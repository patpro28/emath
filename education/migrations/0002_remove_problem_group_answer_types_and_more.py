# Generated by Django 4.0.2 on 2022-06-04 16:22

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('education', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='problem',
            name='group',
        ),
        migrations.AddField(
            model_name='answer',
            name='types',
            field=models.CharField(default='mc', max_length=10, verbose_name='Answer type'),
        ),
        migrations.AddField(
            model_name='problem',
            name='answer_type',
            field=models.CharField(choices=[('mc', 'Multiple-choice'), ('fill', 'Fill in the answer')], default='mc', max_length=10, verbose_name='Type of answer'),
        ),
        migrations.AddField(
            model_name='problem',
            name='types',
            field=models.ManyToManyField(blank=True, help_text='The group of problem, shown under Category in the problem list.', related_name='problem', to='education.ProblemGroup', verbose_name='group'),
        ),
        migrations.AlterField(
            model_name='problem',
            name='level',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='education.level', verbose_name='level'),
        ),
    ]
