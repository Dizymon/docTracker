from django.test import TestCase
from django.contrib import admin
from django.contrib.auth.models import User
from django.test import RequestFactory
from django.urls import reverse

from .admin import DocumentAdmin, DocumentAdminForm
from .forms import CUSTOM_STATUS_VALUE, DocumentForm
from .models import Document, DocumentStatus, UserProfile


class DocumentStatusPermissionTests(TestCase):
    def setUp(self):
        self.creator = User.objects.create_user(username='creator', password='password')
        self.assignee = User.objects.create_user(username='assignee', password='password')
        self.admin_user = User.objects.create_user(username='admin', password='password', is_staff=True)
        self.hr_user = User.objects.create_user(username='hr', password='password')
        UserProfile.objects.create(user=self.hr_user, role=UserProfile.ROLE_HR)
        self.document = Document.objects.create(
            title='Policy',
            description='Initial draft',
            status='draft',
            created_by=self.creator,
            assigned_to=self.assignee,
        )

    def form_payload(self, status, status_note='Moving through workflow'):
        return {
            'title': self.document.title,
            'description': self.document.description,
            'category': '',
            'status': status,
            'custom_status': '',
            'priority': self.document.priority,
            'tags': self.document.tags,
            'assigned_to': self.assignee.pk,
            'due_date': '',
            'status_note': status_note,
        }

    def test_status_field_is_disabled_for_creator_when_not_assigned(self):
        form = DocumentForm(instance=self.document, user=self.creator)

        self.assertTrue(form.fields['status'].disabled)

    def test_creator_cannot_change_status_when_not_assigned(self):
        self.client.force_login(self.creator)

        response = self.client.post(
            reverse('document_edit', args=[self.document.pk]),
            self.form_payload('review'),
        )

        self.assertRedirects(response, reverse('document_detail', args=[self.document.pk]))
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, 'draft')

    def test_assigned_user_can_change_status(self):
        self.client.force_login(self.assignee)

        response = self.client.post(
            reverse('document_edit', args=[self.document.pk]),
            self.form_payload('review'),
        )

        self.assertRedirects(response, reverse('document_detail', args=[self.document.pk]))
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, 'review')

    def test_admin_status_is_readonly_for_non_assigned_user(self):
        request = RequestFactory().get('/')
        request.user = self.creator
        document_admin = DocumentAdmin(Document, admin.site)

        self.assertIn('status', document_admin.get_readonly_fields(request, self.document))

    def test_admin_status_is_editable_even_when_not_assigned(self):
        request = RequestFactory().get('/')
        request.user = self.admin_user
        document_admin = DocumentAdmin(Document, admin.site)

        self.assertNotIn('status', document_admin.get_readonly_fields(request, self.document))

    def test_custom_status_can_be_selected(self):
        returned = DocumentStatus.objects.create(code='returned', label='Returned')
        draft = DocumentStatus.objects.get(code='draft')
        draft.allowed_next_statuses.add(returned)
        self.client.force_login(self.assignee)

        response = self.client.post(
            reverse('document_edit', args=[self.document.pk]),
            self.form_payload('returned'),
        )

        self.assertRedirects(response, reverse('document_detail', args=[self.document.pk]))
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, 'returned')
        self.assertEqual(self.document.get_status_display(), 'Returned')

    def test_document_form_status_field_suggests_existing_statuses(self):
        form = DocumentForm(instance=self.document, user=self.assignee)

        self.assertEqual(form.fields['status'].choices[-1], (CUSTOM_STATUS_VALUE, 'Custom...'))
        self.assertIn(('draft', 'Draft'), form.fields['status'].choices)
        self.assertIn(('archived', 'Archived'), form.fields['status'].choices)

    def test_document_form_accepts_typed_custom_status(self):
        self.client.force_login(self.assignee)
        payload = self.form_payload(CUSTOM_STATUS_VALUE)
        payload['custom_status'] = 'Waiting for Signature'

        response = self.client.post(
            reverse('document_edit', args=[self.document.pk]),
            payload,
        )

        self.assertRedirects(response, reverse('document_detail', args=[self.document.pk]))
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, 'Waiting for Signature')

    def test_status_change_requires_comment(self):
        self.client.force_login(self.assignee)

        response = self.client.post(
            reverse('document_edit', args=[self.document.pk]),
            self.form_payload('review', status_note=''),
        )

        self.assertEqual(response.status_code, 200)
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, 'draft')

    def test_hr_role_can_manage_unassigned_document(self):
        self.client.force_login(self.hr_user)

        response = self.client.post(
            reverse('document_edit', args=[self.document.pk]),
            self.form_payload('review'),
        )

        self.assertRedirects(response, reverse('document_detail', args=[self.document.pk]))
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, 'review')

    def test_admin_form_accepts_typed_custom_status(self):
        form = DocumentAdminForm(data={
            'title': self.document.title,
            'description': self.document.description,
            'category': '',
            'status': CUSTOM_STATUS_VALUE,
            'custom_status': 'Waiting for Signature',
            'priority': self.document.priority,
            'tags': self.document.tags,
            'created_by': self.creator.pk,
            'assigned_to': self.assignee.pk,
            'due_date': '',
        }, instance=self.document)

        self.assertTrue(form.is_valid(), form.errors)
        doc = form.save()
        self.assertEqual(doc.status, 'Waiting for Signature')
        self.assertEqual(doc.status_badge_class, 'waiting-for-signature')

    def test_admin_form_status_field_suggests_existing_statuses(self):
        form = DocumentAdminForm(instance=self.document)

        self.assertEqual(form.fields['status'].choices[-1], (CUSTOM_STATUS_VALUE, 'Custom...'))
        self.assertIn(('draft', 'Draft'), form.fields['status'].choices)
