from collections import namedtuple
from functools import partial
from itertools import chain
from operator import attrgetter
import random
from django import forms
from django.db import IntegrityError
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views.generic import ListView, DetailView
from django.views.generic.detail import BaseDetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.utils.functional import cached_property
from django.db.models import Q, F, Max
from backend.utils.ranker import ranker

from backend.utils.views import generic_message, QueryStringSortMixin, TitleMixin, DiggPaginatorMixin
from education.models import Contest
from education.models.contest import ContestParticipation, ContestProblem
from education.models.problem import Answer
from education.models.submission import Submission, SubmissionProblem

class PrivateContestError(Exception):
    def __init__(self, name, is_private, is_organization_private, orgs):
        self.name = name
        self.is_private = is_private
        self.is_organization_private = is_organization_private
        self.orgs = orgs

class ContestMixin(object):
  context_object_name = 'contest'
  slug_field = 'key'
  slug_url_kwarg = 'contest'
  model = Contest
  tab = None

  def get_tab(self):
    return self.tab

  def get_object(self, queryset=None):
    contest = super().get_object(queryset)
    user = self.request.user
    try:
      contest.access_check(user)
    except Contest.PrivateContest:
      raise PrivateContestError(contest.name, contest.is_private, contest.is_organization_private,
                                contest.organizations.all())
    except Contest.Inaccessible:
      raise Http404
    else:
      return contest

  def no_such_contest(self):
    key = self.kwargs.get(self.slug_url_kwarg, None)
    return generic_message(self.request, _('No such contest'),
                          _('Could not find a contest with the key "%s".') % key, status=404)

  @cached_property
  def is_editor(self):
    if not self.request.user.is_authenticated:
      return False
    return self.request.user.id in self.object.editor_ids

  @cached_property
  def can_edit(self):
    return self.object.is_editable_by(self.request.user)

  def get_context_data(self, **kwargs):
      context = super().get_context_data(**kwargs)
      context["now"] = timezone.now()
      context['is_editor'] = self.is_editor
      context['can_edit'] = self.can_edit
      context['tab'] = self.get_tab()

      if self.request.user.is_authenticated:
        try:
          context['live_participation'] = (
            self.request.user.contest_history.get(
              contest=self.object,
              virtual=ContestParticipation.LIVE
            )
          )
        except ContestParticipation.DoesNotExist:
          context['live_participation'] = None
          context['has_joined'] = False
        else:
          context['has_joined'] = True
      else:
        context['live_participation'] = None
        context['has_joined'] = False
      context['logo_override_image'] = self.object.logo_override_image
      if not context['logo_override_image'] and self.object.organizations.count() == 1:
        context['logo_override_image'] = self.object.organizations.first().logo
      
      return context
  

  def get(self, request, *args, **kwargs):
    try:
      return super().get(request, *args, **kwargs)
    except Http404:
      return self.no_such_contest()


class ContestListMixin(object):
  def get_queryset(self):
    return Contest.get_visible_contests(self.request.user)


class ContestList(QueryStringSortMixin, TitleMixin, ContestListMixin, DiggPaginatorMixin, ListView):
  model = Contest
  template_name = 'contest/list.html'
  title = _('Contests')
  context_object_name = 'contests'
  paginate_by = 20
  all_sorts = frozenset(('name', 'user_count', 'start_time'))
  default_desc = frozenset(('name', 'user_count'))
  default_sort = '-start_time'

  @cached_property
  def _now(self):
    return timezone.now()
  
  def _get_queryset(self):
    return super().get_queryset().prefetch_related('organizations', 'authors', 'curators')

  def get_queryset(self):
    return self._get_queryset().filter(end_time__lt=self._now).order_by(self.order, 'key')
    
  def get_context_data(self, **kwargs):
      context = super().get_context_data(**kwargs)
      present, active, future = [], [], []
      for contest in self._get_queryset().exclude(end_time__lt=self._now):
        if contest.start_time > self._now:
          future.append(contest)
        else:
          present.append(contest)
      
      if self.request.user.is_authenticated:
        for participation in ContestParticipation.objects.filter(virtual=0, user=self.request.user, contest_id__in=present) \
                              .select_related('contest') \
                              .prefetch_related('contest__authors', 'contest__curators') \
                              .annotate(key=F('contest__key')):
          if not participation.ended:
            active.append(participation)
            present.remove(participation.contest)
      
      active.sort(key=attrgetter('end_time', 'key'))
      present.sort(key=attrgetter('end_time', 'key'))
      future.sort(key=attrgetter('start_time'))

      context['active_participations'] = active
      context['current_contests'] = present
      context['future_contests'] = future
      context['now'] = self._now
      context['first_page_href'] = '.'
      context['page_suffix'] = '#past-contests'
      context.update(self.get_sort_context())
      context.update(self.get_sort_paginate_context())
      return context
  

class ContestDetail(ContestMixin, TitleMixin, DetailView):
  template_name = 'contest/contest.html'
  tab = 'info'

  def get_title(self):
    return self.object.name
  

class ContestAccessDenied(Exception):
  pass


class ContestAccessForm(forms.Form):
  access_code = forms.CharField(max_length=255)

  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.fields['access_code'].widget.attrs.update({'autocomplete': 'off'})

class ContestJoin(LoginRequiredMixin, ContestMixin, BaseDetailView):
  def get(self, request, *args, **kwargs):
    self.object = self.get_object()
    user = request.user
    if user.current_contest is not None:
      if user.current_contest.contest == self.object:
        return HttpResponseRedirect(reverse('education:contest_detail', kwargs={'contest': self.object.key}))
      return generic_message(request, _('Already in contest'),
                            _('You are already in a contest "%s".') % user.current_contest.contest.name)
    
    return self.ask_for_access_code()

  def post(self, request, *args, **kwargs):
    self.object = self.get_object()
    try:
      return self.join_contest(request)
    except ContestAccessDenied:
      if request.POST.get('access_code'):
        return self.ask_for_access_code(ContestAccessForm(request.POST))
      else:
        return HttpResponseRedirect(request.path)
  
  def join_contest(self, request, access_code=None):
    contest = self.object

    if not contest.can_join and not self.is_editor:
      return generic_message(request, _('Contest not ongoing'),
                            _('"%s" is not currently ongoing.') % contest.name)
    
    user = request.user
    if user.current_contest is not None:
      return generic_message(request, _('Already in contest'),
                            _('You are already in a contest "%s".') % user.current_contest.contest.name)
    
    if not user.is_superuser and contest.banned_users.filter(id=user.id).exists():
      return generic_message(request, _('Banned from joining'),
                            _('You have been declared persona non grata for this contest. '
                              'You are permanently barred from joining this contest.'))
    
    required_access_code = (not self.can_edit and contest.access_code and access_code != contest.access_code)

    if contest.ended:
      if required_access_code:
        raise ContestAccessDenied()
      
      while True:
        virtual_id = max((ContestParticipation.objects.filter(contest=contest, user=user)
                          .aggregate(virtual_id=Max('virtual'))['virtual_id'] or 0) + 1, 1)
        try:
          participation = ContestParticipation.objects.create(
            contest=contest,
            user=user,
            virtual=virtual_id,
            real_start=timezone.now()
          )
        except IntegrityError:
          pass
        else:
          break
    else:
      SPECTATE = ContestParticipation.SPECTATE
      LIVE = ContestParticipation.LIVE

      try:
        participation = ContestParticipation.objects.get(
          contest=contest, user=user, virtual=(SPECTATE if self.is_editor else LIVE)
        )
      except ContestParticipation.DoesNotExist:
        if required_access_code:
          raise ContestAccessDenied()
        
        participation = ContestParticipation.objects.create(
          contest=contest,
          user=user,
          virtual=(SPECTATE if self.is_editor else LIVE),
          real_start=timezone.now()
        )
      else:
        if participation.ended:
          participation = ContestParticipation.objects.get_or_create(
            contest=contest,
            user=user,
            virtual=SPECTATE,
            defaults={'real_start': timezone.now()}
          )[0]
    
    user.current_contest = participation
    user.save()
    contest._updating_stats_only = True
    contest.update_user_count()
    return HttpResponseRedirect(reverse('education:contest_detail', kwargs={'contest': contest.key}))
  
  def ask_for_access_code(self, form=None):
    contest = self.object
    wrong_code = False
    if form:
      if form.is_valid():
        if form.cleaned_data['access_code'] == contest.access_code:
          return self.join_contest(self.request, form.cleaned_data['access_code'])
        wrong_code = True
    else:
      form = ContestAccessForm()
    return render(self.request, 'contest/access_code.html', {
      'form': form,
      'wrong_code': wrong_code,
      'title': _('Enter access code for "%s"') % contest.name
    })


class ContestLeave(LoginRequiredMixin, ContestMixin, BaseDetailView):
  def post(self, request, *args, **kwargs):
    contest = self.get_object()
    user = request.user
    if user.current_contest is None or user.current_contest.contest_id != contest.id:
      return generic_message(request, _('No such contest'),
                            _('You are not in contest "%s".') % contest.key, status=404)
    
    user.remove_contest()
    return HttpResponseRedirect(reverse('education:contest_detail', kwargs={'contest': contest.key}))


ContestRankingProfile = namedtuple(
  'ContestRankingProfile',
  'id user css_class username points cumtime tiebreaker organization participation '
  'participation_rating problem_cells result_cell',
)

BestSolutionData = namedtuple(
  'BestSolutionData', 'code points time state is_pretested'
)

def make_contest_ranking_profile(contest, participation, contest_problems):
  def display_user_problem(contest_problem):
    try:
      return contest.format.display_user_problem(participation, contest_problem)
    except (KeyError, TypeError, ValueError):
      return mark_safe('<td>???</td>')

  user = participation.user

  return ContestRankingProfile(
    id=user.id,
    user=user,
    css_class=user.css_class,
    username=user.username,
    points=participation.score,
    cumtime=participation.cumtime,
    tiebreaker=participation.tiebreaker,
    organization=user.organization,
    participation_rating=participation.rating.rating if hasattr(participation, 'rating') else None,
    problem_cells=[display_user_problem(problem) for problem in contest_problems],
    result_cell=contest.format.display_participation_result(participation),
    participation=participation
  )

def base_contest_ranking_list(contest, problems, queryset):
  return [make_contest_ranking_profile(contest, participation, problems) for participation in 
          queryset.select_related('user').defer('user__about', 'user__organizations__about')]

def contest_ranking_list(contest, problems):
  return base_contest_ranking_list(contest, problems, contest.users.filter(virtual=0)
                                  .prefetch_related('user__organizations')
                                  .order_by('is_disqualified', '-score', 'cumtime', 'tiebreaker'))

class ContestRankingBase(ContestMixin, TitleMixin, DetailView):
    template_name = 'contest/ranking.html'
    tab = None

    def get_title(self):
        raise NotImplementedError()

    def get_content_title(self):
        return self.object.name

    def get_ranking_list(self):
        raise NotImplementedError()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if not self.object.can_see_own_scoreboard(self.request.user):
            raise Http404()

        users, problems = self.get_ranking_list()
        context['users'] = users
        context['problems'] = problems
        # context['last_msg'] = event.last()
        # context['tab'] = self.tab
        return context

def get_contest_ranking_list(request, contest, participation=None, ranking_list=contest_ranking_list,
                          show_current_virtual=True, ranker=ranker):
    problems = list(contest.contest_problems.select_related('problem').defer('problem__description').order_by('order'))

    users = ranker(ranking_list(contest, problems), key=attrgetter('points', 'cumtime', 'tiebreaker'))

    if show_current_virtual:
        if participation is None and request.user.is_authenticated:
            participation = request.user.current_contest
            if participation is None or participation.contest_id != contest.id:
                participation = None
        if participation is not None and participation.virtual:
            users = chain([('-', make_contest_ranking_profile(contest, participation, problems))], users)
    
    return users, problems


class ContestRanking(ContestRankingBase):
  tab = 'ranking'

  def get_title(self):
    return _('%s Rankings') % self.object.name

  def get_ranking_list(self):
    if not self.object.can_see_full_scoreboard(self.request.user):
      queryset = self.object.users.filter(user=self.request.user, virtual=ContestParticipation.LIVE)
      return get_contest_ranking_list(
        self.request, self.object,
        ranking_list=partial(base_contest_ranking_list, queryset=queryset),
        ranker=lambda users, key: ((_('???'), user) for user in users),
      )

    return get_contest_ranking_list(self.request, self.object)

  def get_context_data(self, **kwargs):
    context = super().get_context_data(**kwargs)
    # context['has_rating'] = self.object.ratings.exists()
    return context


def get_answer_contest_problem(problem):
  ans = list(Answer.objects.filter(problem=problem))
  random.shuffle(ans)
  answer = [(chr(idx + 65), answer.description) for idx, answer in enumerate(ans) ]
  return answer

def get_participation(user, contest):
  LIVE = ContestParticipation.LIVE
  SPETATE = ContestParticipation.SPECTATE
  spectate = user in contest.editor_ids
  if not contest.ended:
    participation = ContestParticipation.objects.get(
      user=user,
      contest=contest,
      virtual=SPETATE if spectate else LIVE
    )
  else:
    participation = ContestParticipation.objects.filter(
      user=user,
      contest=contest,
      virtual__gt=LIVE
    ).order_by('-virtual').first()
  return participation

class ContestTaskView(ContestMixin, TitleMixin, DetailView):
  template_name = 'contest/tasks.html'
  
  def get_title(self):
      return "Contest %(contest)s by %(user)s" % {
        'contest': self.object.name,
        'user': self.request.user.fullname
      }

  def get_context_data(self, **kwargs):
      context = super().get_context_data(**kwargs)
      problems = list(ContestProblem.objects.filter(contest=self.object).order_by('order'))
      random.shuffle(problems)
      user = self.request.user
      contest = self.object
      auth = user.is_authenticated and user.current_contest is not None and user.current_contest.contest == contest
      auth = auth or self.is_editor
      context['problems'] = []
      for problem in problems:
        answer = get_answer_contest_problem(problem.problem)
        context['problems'].append((problem, answer))
      participation = get_participation(user, contest)
      submission = Submission.objects.create(
        user=participation,
        contest=contest,
        result='PE'
      )
      context['submission'] = submission
      return context
  
  def post(self, request, *args, **kwargs):
    key = request.POST.get('contest', None)
    sub_id = request.POST.get('submission', None)
    if key is None or sub_id is None:
      raise Http404
    try:
      contest = Contest.objects.get(key=key)
      submission = Submission.objects.get(id=sub_id)
    except (Contest.DoesNotExist, Submission.DoesNotExist):
      raise Http404

    if submission.problems.exists():
      return generic_message(request, _('Duplicate submission'),
                            _('You must click "Take a test" button to start contest'))

    problems = ContestProblem.objects.filter(contest=contest).select_related('problem').defer('problem__description')
    for problem in problems:
      ans = request.POST.get('answer_' + str(problem.id), None)
      if ans is not None:
        submissionProblem = SubmissionProblem.objects.get_or_create(
          submission=submission,
          problem=problem,
        )[0]
        submissionProblem.output = ans
        submissionProblem.save()
    submission.time = timezone.now()
    # print(submission.id)
    submission.save()
    submission.judge()
    submission.update_contest()

    return HttpResponseRedirect(reverse('education:all_submissions'))
