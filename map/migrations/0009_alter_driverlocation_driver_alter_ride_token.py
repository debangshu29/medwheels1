# Generated by Django 5.0.1 on 2024-04-24 07:44

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('map', '0008_rename_user_driverlocation_driver_alter_ride_token'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name='driverlocation',
            name='driver',
            field=models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='driver_location', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name='ride',
            name='token',
            field=models.CharField(default='8b854e14bb264d04', max_length=32, unique=True),
        ),
    ]