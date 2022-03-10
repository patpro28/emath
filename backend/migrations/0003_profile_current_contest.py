# Generated by Django 4.0.2 on 2022-03-03 08:55

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('education', '0001_initial'),
        ('backend', '0002_remove_profile_last_access'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='current_contest',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='education.contestparticipation', verbose_name='current contest'),
        ),
    ]