# verify/models.py
from django.db import models



class DriverDocuments(models.Model):
    driver = models.ForeignKey('Drivers', models.DO_NOTHING, related_name='documents')
    photo = models.ImageField(upload_to="drivers/photos/")
    license_no = models.CharField(max_length=50, unique=True)
    license_scan = models.FileField(upload_to="drivers/license_scans/")
    issue_date = models.DateField()
    expiry_date = models.DateField()
    vehicle = models.CharField(max_length=100)
    gov_id_number = models.CharField(max_length=50, unique=True)
    gov_id = models.FileField(upload_to="drivers/gov_ids/")
    uploaded_at = models.DateTimeField(blank=True, null=True)
    verified_by = models.ForeignKey(
        'Employees',
        models.DO_NOTHING,
        db_column='verified_by',
        blank=True,
        null=True,
        related_name='verified_driver_documents'
    )
    status = models.CharField(max_length=8, blank=True, null=True)

    class Meta:
        managed = True
        db_table = 'driver_documents'

    def __str__(self):
        return f"{self.driver_id} - {self.vehicle}"


class Drivers(models.Model):
    user = models.ForeignKey('Users', models.DO_NOTHING, related_name='driver_profile')
    full_name = models.CharField(max_length=150)
    gender = models.CharField(max_length=20, choices=[('male', 'Male'), ('female', 'Female'), ('other', 'Other')])
    dob = models.DateField()
    address = models.TextField()
    experience = models.PositiveIntegerField()
    emergency_contact = models.CharField(max_length=255)
    status = models.CharField(
        max_length=20,
        choices=[('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')],
        default='pending'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    verified_by = models.ForeignKey(
        'Employees',
        models.DO_NOTHING,
        db_column='verified_by',
        blank=True,
        null=True,
        related_name='verified_drivers'
    )

    class Meta:
        managed = True
        db_table = 'drivers'

    def __str__(self):
        return f"{self.user_id} - {self.full_name}"


class EmployeeRoles(models.Model):
    # changed OneToOneField -> ForeignKey to reflect (employee, role) composite uniqueness
    employee = models.ForeignKey('Employees', models.DO_NOTHING, related_name='roles')
    role = models.ForeignKey('Roles', models.DO_NOTHING, related_name='employee_roles')
    is_primary = models.IntegerField(blank=True, null=True)
    assigned_by = models.ForeignKey(
        'Employees',
        models.DO_NOTHING,
        db_column='assigned_by',
        related_name='roles_assigned',
        blank=True,
        null=True
    )
    assigned_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = True
        db_table = 'employee_roles'
        unique_together = (('employee', 'role'),)

    def __str__(self):
        return f"Employee {self.employee_id} - Role {self.role_id}"


class Employees(models.Model):
    user = models.ForeignKey('Users', models.DO_NOTHING, related_name='employee_profile')
    organization = models.ForeignKey('Organizations', models.DO_NOTHING, related_name='employees')
    employee_code = models.CharField(unique=True, max_length=100, blank=True, null=True)
    department = models.CharField(max_length=100, blank=True, null=True)
    designation = models.CharField(max_length=100, blank=True, null=True)
    date_of_joining = models.DateField(blank=True, null=True)
    date_of_leaving = models.DateField(blank=True, null=True)
    employment_type = models.CharField(max_length=9, blank=True, null=True)
    salary = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    reporting_manager = models.ForeignKey('self', models.DO_NOTHING, blank=True, null=True, related_name='subordinates')
    work_email = models.CharField(unique=True, max_length=255, blank=True, null=True)
    work_phone = models.CharField(unique=True, max_length=20, blank=True, null=True)
    address = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=10, blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = True
        db_table = 'employees'

    def __str__(self):
        return f"{self.user_id} ({self.employee_code or 'no-code'})"


class Organizations(models.Model):
    name = models.CharField(max_length=255)
    email = models.CharField(unique=True, max_length=255, blank=True, null=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    website = models.CharField(max_length=255, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    gst_number = models.CharField(max_length=100, blank=True, null=True)
    established_at = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = True
        db_table = 'organizations'

    def __str__(self):
        return self.name or f"Organization {self.pk}"


class Roles(models.Model):
    name = models.CharField(unique=True, max_length=100)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = True
        db_table = 'roles'

    def __str__(self):
        return self.name


class Users(models.Model):
    organization = models.ForeignKey(Organizations, models.DO_NOTHING, blank=True, null=True, related_name='users')
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True, max_length=255)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    password = models.CharField(max_length=255, blank=True, null=True)
    auth_provider = models.CharField(max_length=6, blank=True, null=True)  # values like 'local'|'google'
    profile_picture = models.CharField(max_length=500, blank=True, null=True)
    user_type = models.CharField(max_length=8)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = True
        db_table = 'users'

    def __str__(self):
        return f"{self.name} <{self.email}>"
