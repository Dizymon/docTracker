from django import forms
from django.contrib.auth.models import User
from .models import Document, DocumentStatus, Category, Comment, UserProfile, user_has_role


CUSTOM_STATUS_VALUE = '__custom__'


def get_document_status_choices(include_blank=False):
    statuses = list(DocumentStatus.objects.values_list('code', 'label').order_by('label'))
    existing_codes = {code for code, _ in statuses}
    choices = statuses + [
        (code, label) for code, label in Document.STATUS_CHOICES
        if code not in existing_codes
    ]
    if include_blank:
        return [('', 'All Statuses')] + choices
    return choices


def get_allowed_status_choices(document):
    choices = get_document_status_choices()
    if not document or not document.pk:
        return choices

    current = DocumentStatus.objects.filter(code=document.status).first()
    if not current or not current.allowed_next_statuses.exists():
        return choices

    allowed_codes = set(current.allowed_next_statuses.values_list('code', flat=True))
    allowed_codes.add(document.status)
    return [(code, label) for code, label in choices if code in allowed_codes]


def can_edit_status(user, document):
    if not user or not user.is_authenticated or not document or not document.pk:
        return False
    return (
        user.is_staff or user.is_superuser or
        user_has_role(user, UserProfile.ROLE_ADMIN, UserProfile.ROLE_HR) or
        document.assigned_to_id == user.id
    )


def can_edit_file(user, document):
    if not document or not document.pk:
        return True
    return (
        user.is_staff or user.is_superuser or
        document.created_by_id == user.id or
        document.assigned_to_id == user.id
    )


class DocumentForm(forms.ModelForm):
    status = forms.ChoiceField(required=False)
    custom_status = forms.CharField(
        required=False,
        label='Custom Status',
        widget=forms.TextInput(attrs={'placeholder': 'Type a custom status'}),
        help_text='Use this only if the status is not in the list.',
    )
    status_note = forms.CharField(
        required=False,
        label='Status / approval comment',
        widget=forms.Textarea(attrs={
            'rows': 2,
            'placeholder': 'Required when changing status',
        }),
    )

    class Meta:
        model = Document
        fields = ['title', 'description', 'category', 'status', 'priority', 'file', 'tags', 'assigned_to', 'due_date']
        widgets = {
            'due_date': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 3}),
            'tags': forms.TextInput(attrs={'placeholder': 'e.g. finance, report, Q1'}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self.fields['assigned_to'].queryset = User.objects.all()
        self.fields['assigned_to'].empty_label = "-- Unassigned --"
        self.fields['category'].empty_label = "-- No Category --"
        allowed_statuses = get_allowed_status_choices(self.instance)
        self.fields['status'].choices = allowed_statuses + [(CUSTOM_STATUS_VALUE, 'Custom...')]
        current_status = self.instance.status if self.instance and self.instance.pk else ''
        allowed_codes = {code for code, _ in allowed_statuses}
        if current_status and current_status not in allowed_codes:
            self.fields['status'].initial = CUSTOM_STATUS_VALUE
            self.fields['custom_status'].initial = current_status
        elif current_status:
            self.fields['status'].initial = current_status
        elif allowed_statuses:
            self.fields['status'].initial = allowed_statuses[0][0]
        self.fields['status'].help_text = 'Choose an existing status, or pick Custom to type your own.'
        if self.instance and self.instance.pk and not can_edit_status(self.user, self.instance):
            self.fields['status'].disabled = True
            self.fields['status'].help_text = 'Only the assigned user or an admin can change status.'
            self.fields['custom_status'].disabled = True
            self.fields['status_note'].disabled = True
        if self.instance and self.instance.pk and not can_edit_file(self.user, self.instance):
            self.fields['file'].disabled = True
            self.fields['file'].help_text = 'Only the creator, assigned user, or an admin can change the attached file.'

    def clean(self):
        cleaned_data = super().clean()
        status = cleaned_data.get('status')
        custom_status = cleaned_data.get('custom_status', '').strip()
        status_note = cleaned_data.get('status_note', '').strip()
        old_status = self.instance.status if self.instance and self.instance.pk else None
        if status == CUSTOM_STATUS_VALUE:
            if not custom_status:
                self.add_error('custom_status', 'Enter a custom status.')
            status = custom_status
            cleaned_data['status'] = status

        if old_status and status != old_status:
            known_statuses = {code for code, _ in get_document_status_choices()}
            valid_statuses = {code for code, _ in get_allowed_status_choices(self.instance)}
            if status in known_statuses and status not in valid_statuses:
                raise forms.ValidationError('This status change is not allowed by the workflow rules.')
            if not status_note:
                self.add_error('status_note', 'Add a comment before changing status.')
        return cleaned_data


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'description']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 2}),
        }


class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ['text']
        widgets = {
            'text': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Add a comment...'}),
        }
        labels = {'text': ''}


class DocumentFilterForm(forms.Form):
    search = forms.CharField(required=False, widget=forms.TextInput(attrs={'placeholder': 'Search title, tags, or file name...'}))
    status = forms.ChoiceField(required=False)
    priority = forms.ChoiceField(required=False, choices=[('', 'All Priorities')] + Document.PRIORITY_CHOICES)
    due = forms.ChoiceField(required=False, choices=[
        ('', 'All Due Dates'),
        ('overdue', 'Overdue'),
        ('soon', 'Due Soon'),
        ('none', 'No Due Date'),
    ])
    category = forms.ModelChoiceField(required=False, queryset=Category.objects.all(), empty_label="All Categories")
    assigned_to = forms.ModelChoiceField(required=False, queryset=User.objects.all(), empty_label="All Users")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['status'].choices = get_document_status_choices(include_blank=True)
