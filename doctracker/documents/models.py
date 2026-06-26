from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.text import slugify
from datetime import timedelta


class UserProfile(models.Model):
    ROLE_ADMIN = 'admin'
    ROLE_HR = 'hr'
    ROLE_EMPLOYEE = 'employee'
    ROLE_CHOICES = [
        (ROLE_ADMIN, 'Admin'),
        (ROLE_HR, 'HR'),
        (ROLE_EMPLOYEE, 'Employee'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_EMPLOYEE)
    department = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['user__username']

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"


def get_user_role(user):
    if not user or not user.is_authenticated:
        return UserProfile.ROLE_EMPLOYEE
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile.role


def user_has_role(user, *roles):
    return get_user_role(user) in roles


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ['name']

    def __str__(self):
        return self.name


class DocumentStatus(models.Model):
    code = models.SlugField(max_length=20, unique=True)
    label = models.CharField(max_length=50)
    allowed_next_statuses = models.ManyToManyField(
        'self',
        symmetrical=False,
        blank=True,
        related_name='previous_statuses',
        help_text="Statuses a document can move to from this status.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Document statuses"
        ordering = ['label']

    def __str__(self):
        return self.label


class Document(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('review', 'Under Review'),
        ('approved', 'Approved'),
        ('archived', 'Archived'),
    ]
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=50, default='draft')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='normal')
    file = models.FileField(upload_to='documents/', null=True, blank=True)
    tags = models.CharField(max_length=500, blank=True, help_text="Comma-separated tags")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_docs')
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_docs')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    due_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    def get_tags_list(self):
        return [t.strip() for t in self.tags.split(',') if t.strip()]

    def get_status_display(self):
        status = DocumentStatus.objects.filter(code=self.status).first()
        if status:
            return status.label
        return dict(self.STATUS_CHOICES).get(self.status, self.status)

    @property
    def status_badge_class(self):
        return slugify(self.status) or 'custom'

    @property
    def is_overdue(self):
        return bool(self.due_date and self.due_date < timezone.localdate() and self.status not in ['approved', 'archived'])

    @property
    def is_due_soon(self):
        if not self.due_date or self.status in ['approved', 'archived']:
            return False
        today = timezone.localdate()
        return today <= self.due_date <= today + timedelta(days=7)


class DocumentHistory(models.Model):
    CHANGE_TYPES = [
        ('created', 'Created'),
        ('updated', 'Updated'),
        ('status', 'Status changed'),
        ('file', 'File changed'),
        ('comment', 'Comment added'),
    ]

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='history')
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    change_type = models.CharField(max_length=20, choices=CHANGE_TYPES, default='updated')
    change_note = models.TextField()
    old_status = models.CharField(max_length=50, blank=True)
    new_status = models.CharField(max_length=50, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.document.title} - {self.timestamp:%Y-%m-%d %H:%M}"


class DocumentFileVersion(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='file_versions')
    file = models.FileField(upload_to='documents/versions/')
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.document.title} - {self.uploaded_at:%Y-%m-%d %H:%M}"


class Comment(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Comment by {self.author} on {self.document.title}"
