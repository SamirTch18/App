# -*- coding: utf-8 -*-
# Generated by Django 1.10.5 on 2019-01-18 20:58
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('yumfoodapp', '0006_auto_20190117_2247'),
    ]

    operations = [
        migrations.AddField(
            model_name='driver',
            name='location',
            field=models.CharField(blank=True, max_length=500),
        ),
    ]