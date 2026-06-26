from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django import forms
from .models import Document, DocumentStatus, Category, DocumentHistory, DocumentFileVersion, Comment, UserProfile
from .forms import CUSTOM_STATUS_VALUE, can_edit_status, get_document_status_choices


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    extra = 0
    max_num = 1


class UserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline,)


admin.site.unregister(User)
admin.site.register(User, UserAdmin)


class DocumentAdminForm(forms.ModelForm):
    status = forms.ChoiceField(required=False)
    custom_status = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Type a custom status'}),
        help_text='Use this only if the status is not in the list.',
    )

    class Meta:
        model = Document
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        status_choices = get_document_status_choices()
        self.fields['status'].choices = status_choices + [(CUSTOM_STATUS_VALUE, 'Custom...')]
        current_status = self.instance.status if self.instance and self.instance.pk else ''
        existing_codes = {code for code, _ in status_choices}
        if current_status and current_status not in existing_codes:
            self.fields['status'].initial = CUSTOM_STATUS_VALUE
            self.fields['custom_status'].initial = current_status
        elif current_status:
            self.fields['status'].initial = current_status

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('status') == CUSTOM_STATUS_VALUE:
            custom_status = cleaned_data.get('custom_status', '').strip()
            if not custom_status:
                self.add_error('custom_status', 'Enter a custom status.')
            cleaned_data['status'] = custom_status
        return cleaned_data


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    form = DocumentAdminForm
    list_display = ('title', 'status', 'priority', 'due_date', 'created_by', 'assigned_to', 'updated_at')
    list_filter = ('status', 'priority', 'assigned_to', 'category')
    search_fields = ('title', 'description', 'tags', 'file')

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = list(super().get_readonly_fields(request, obj))
        if obj and not can_edit_status(request.user, obj):
            readonly_fields.append('status')
        return readonly_fields


@admin.register(DocumentStatus)
class DocumentStatusAdmin(admin.ModelAdmin):
    list_display = ('label', 'code', 'created_at')
    search_fields = ('label', 'code')
    prepopulated_fields = {'code': ('label',)}
    filter_horizontal = ('allowed_next_statuses',)


@admin.register(DocumentFileVersion)
class DocumentFileVersionAdmin(admin.ModelAdmin):
    list_display = ('document', 'file', 'uploaded_by', 'uploaded_at')
    list_filter = ('uploaded_at', 'uploaded_by')
    search_fields = ('document__title', 'file', 'note')


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'department')
    list_filter = ('role', 'department')
    search_fields = ('user__username', 'user__email', 'department')


admin.site.register(Category)
admin.site.register(DocumentHistory)
admin.site.register(Comment)
