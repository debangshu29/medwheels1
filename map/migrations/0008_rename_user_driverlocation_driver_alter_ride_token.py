# Generated by Django 5.0.1 on 2024-04-23 18:35

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('map', '0007_remove_ride_driver1_alter_ride_driver_and_more'),
    ]

    operations = [
        migrations.RenameField(
            model_name='driverlocation',
            old_name='user',
            new_name='driver',
        ),
        migrations.AlterField(
            model_name='ride',
            name='token',
            field=models.CharField(default='0c2e3b0aa4374f89', max_length=32, unique=True),
        ),
    ]
