from django.contrib import admin
from .models import Subject, Exam, ExamAttempt, ExamAssignment, ExamGroupPermission


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_at']
    search_fields = ['name']


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ['title', 'subject', 'exam_type', 'start_time', 'end_time', 'is_active', 'created_by']
    list_filter = ['exam_type', 'is_active', 'subject']
    search_fields = ['title', 'subject__name']
    date_hierarchy = 'start_time'
    
    fieldsets = (
        ('Asosiy ma\'lumotlar', {
            'fields': ('title', 'subject', 'exam_type', 'description')
        }),
        ('Imtihon sozlamalari', {
            'fields': ('duration', 'total_marks', 'passing_marks')
        }),
        ('Vaqt sozlamalari', {
            'fields': ('start_time', 'end_time', 'is_active')
        }),
        ('Qo\'shimcha', {
            'fields': ('created_by',)
        }),
    )


@admin.register(ExamAssignment)
class ExamAssignmentAdmin(admin.ModelAdmin):
    list_display = ['subject', 'group', 'teacher', 'admin_start_time', 'admin_deadline', 'assigned_by', 'created_at']
    list_filter = ['teacher', 'subject', 'group']
    search_fields = ['subject__name', 'group__name', 'teacher__first_name', 'teacher__last_name']
    raw_id_fields = ['subject', 'group', 'teacher', 'assigned_by']


@admin.register(ExamGroupPermission)
class ExamGroupPermissionAdmin(admin.ModelAdmin):
    list_display = ['exam', 'group', 'teacher', 'deadline', 'is_active', 'created_at']
    list_filter = ['is_active', 'group', 'teacher']
    search_fields = ['exam__title', 'group__name']
    raw_id_fields = ['exam', 'teacher']


@admin.register(ExamAttempt)
class ExamAttemptAdmin(admin.ModelAdmin):
    list_display = ['student', 'exam', 'status', 'started_at', 'completed_at']
    list_filter = ['status', 'exam']
    search_fields = ['student__username', 'student__first_name', 'student__last_name', 'exam__title']
    date_hierarchy = 'started_at'
