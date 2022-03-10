import urllib

from django.db import ProgrammingError
from django.http import Http404
from django.db.models import Q
from django.views.generic import DetailView, ListView
from django.utils.translation import gettext_lazy as _
from django.utils.functional import cached_property
from backend.utils.diggpaginator import DiggPaginator

from education.models import Problem, ProblemGroup
from backend.models import Profile
from backend.utils.views import QueryStringSortMixin, TitleMixin, generic_message
from backend.utils.strings import safe_int_or_none, safe_float_or_none
from education.models.problem import Answer, Level

class ProblemMixin(object):
    context_object_name = 'problem'
    model = Problem
    slug_field = 'code'
    slug_url_kwarg = 'problem'

    def get_object(self, queryset=None):
        problem = super().get_object(queryset)
        if not problem.is_accessible_by(self.request.user):
            raise Http404
        return problem
    
    def no_such_problem(self):
        code = self.kwargs.get(self.slug_url_kwarg, None)
        return generic_message(self.request, _('No such problem'),
                                _('Could not find a problem with the code "%s".') % code, status=404)
    
    def get(self, request, *args, **kwargs):
        try:
            return super().get(request, *args, **kwargs)
        except Http404:
            return self.no_such_problem()


class ProblemListMixin(object):
    def get_queryset(self):
        return Problem.get_visible_problems(self.request.user)


class ProblemList(TitleMixin, ListView):
    model = Problem
    title = _('Problems')
    template_name = 'problem/list.html'
    limit_show = 50

    @cached_property
    def profile(self):
        if not self.request.user.is_authenticated:
            return None
        return self.request.user

    def get_queryset(self):
        filter = Q(is_public=True)
        if self.request.user.is_authenticated:
            filter |= Q(authors=self.profile)
        
        queryset = Problem.objects.filter(filter).select_related('group').defer('description')
        if not self.request.user.has_perm('education.see_organization_problem'):
            filter = Q(is_organization_private=False)
            if self.profile is not None:
                filter |= Q(organizations__in=self.profile.organizations.all())
            queryset = queryset.filter(filter)
        
        return queryset.distinct()
  

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # context["category"] = self.category
        levels = Level.objects.all()
        queryset = self.get_queryset()
        context['levels'] = []
        for level in levels:
            problems = queryset.filter(level=level)
            if problems.count() > self.limit_show:
                problems = problems[:self.limit_show - 1]
                has_more = True
            else:
                has_more = False
            context['levels'].append({
                'level'   : level,
                'problems': problems,
                'has_more': has_more
            })
        return context


class ProblemLevelList(QueryStringSortMixin, TitleMixin, ListView):
    model = Level
    context_object_name = 'problems'
    template_name = 'problem/level_list.html'
    paginate_by = 1
    sql_sort = frozenset(('difficult', 'code', 'name'))
    manual_sort = frozenset(('group'))
    all_sorts = sql_sort | manual_sort
    default_desc = frozenset(('-difficult'))
    default_sort = 'code'
    slug_field = 'code'
    slug_url_kwarg = 'level'

    def get_object(self):
        code = self.kwargs.get(self.slug_url_kwarg, None)
        return Level.objects.get(code=code)

    def get_title(self):
        return self.get_object().name

    def get_paginator(self, queryset, per_page, orphans=0, allow_empty_first_page=True, **kwargs):
        paginator = DiggPaginator(queryset, per_page, body=6, padding=2, orphans=orphans, 
                                  allow_empty_first_page=allow_empty_first_page, **kwargs)
        paginator.num_pages
        sort_key = self.order.lstrip('-')
        if sort_key in self.sql_sort:
            queryset = queryset.order_by(self.order, 'id')
        elif sort_key == 'group':
            queryset = queryset.order_by(self.order + '__name', 'id')
        
        paginator.object_list = queryset
        return paginator

    @cached_property
    def user(self):
        if self.request.user.is_authenticated:
            return self.request.user
        return None
    
    def get_queryset(self):
        filter = Q(is_public=True)
        if self.user is not None:
            filter |= Q(authors=self.user)
        
        queryset = Problem.objects.filter(filter).select_related('group').defer('description')

        if not self.user.has_perm('education:see_organization_problem'):
            filter = Q(is_organization_private=False)
            if self.user is not None:
                filter |= Q(organizations__in=self.user.organizations.all())
            queryset = queryset.filter(filter)
        
        return queryset.distinct()
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        context.update(self.get_sort_paginate_context())
        context.update(self.get_sort_context())
        context['level'] = self.get_object()
        return context


def get_answer(problem):
    answers = Answer.objects.filter(problem=problem)
    answer = [(chr(idx + 65), answer.description) for idx, answer in enumerate(answers) ]
    return answer


class ProblemDetail(ProblemMixin, TitleMixin, DetailView):
    context_object_name = 'problem'
    template_name = 'problem/problem.html'

    def get_content_title(self):
        return _('Problem: %s') % self.object.name
    
    def get_title(self):
        return self.object.name

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        # authed = user.is_authenticated
        context['can_edit'] = self.object.is_editable_by(user)
        context['description'] = self.object.description

        if user.is_staff or user.is_superuser:
            context['answers'] = get_answer(self.object)

        return context


