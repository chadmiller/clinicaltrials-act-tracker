# Generated by Django 2.0 on 2018-01-22 11:47

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('frontend', '0018_trial_days_late'),
    ]

    operations = [
        migrations.AlterField(
            model_name='trial',
            name='days_late',
            field=models.IntegerField(blank=True, default=None, null=True),
        ),
    ]
