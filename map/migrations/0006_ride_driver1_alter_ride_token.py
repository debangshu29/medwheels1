# Generated by Django 5.0.1 on 2024-04-21 18:10

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('map', '0005_ride_code_alter_ride_token'),
        ('verify', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='ride',
            name='driver1',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='verify.driver', unique=True),
        ),
        migrations.AlterField(
            model_name='ride',
            name='token',
            field=models.CharField(default='65be37a89feb4120', max_length=32, unique=True),
        ),
    ]
