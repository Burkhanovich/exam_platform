from django.urls import path
from . import views

app_name = 'exams'

urlpatterns = [
    path('', views.exam_list, name='exam_list'),
    path('<int:exam_id>/', views.exam_detail, name='exam_detail'),
    path('<int:exam_id>/start/', views.start_exam, name='start_exam'),
    path('<int:exam_id>/take/', views.take_exam, name='take_exam'),
    path('my-exams/', views.my_exams, name='my_exams'),

    # O'qituvchi sahifalari
    path('teacher/', views.teacher_dashboard, name='teacher_dashboard'),
    path('teacher/grant/<int:assignment_id>/', views.grant_permission, name='grant_permission'),
    path('teacher/revoke/<int:permission_id>/', views.revoke_permission, name='revoke_permission'),
    path('teacher/results/<int:exam_id>/', views.teacher_results, name='teacher_results'),
    path('teacher/create-exam/', views.teacher_create_exam, name='teacher_create_exam'),
    path('teacher/my-tests/', views.teacher_my_tests, name='teacher_my_tests'),
    path('teacher/edit-exam/<int:exam_id>/', views.teacher_edit_exam, name='teacher_edit_exam'),
    path('teacher/delete-exam/<int:exam_id>/', views.teacher_delete_exam, name='teacher_delete_exam'),

    # Admin o'qituvchi boshqaruvi
    path('admin-panel/teachers/', views.admin_teachers, name='admin_teachers'),
    path('admin-panel/teachers/create/', views.admin_create_teacher, name='admin_create_teacher'),
    path('admin-panel/teachers/edit/<int:teacher_id>/', views.admin_edit_teacher, name='admin_edit_teacher'),
    path('admin-panel/teachers/delete/<int:teacher_id>/', views.admin_delete_teacher, name='admin_delete_teacher'),

    # Admin ruxsat berish sahifalari
    path('admin-panel/assignments/', views.admin_assignments, name='admin_assignments'),
    path('admin-panel/assignments/create/', views.admin_create_assignment, name='admin_create_assignment'),
    path('admin-panel/assignments/delete/<int:assignment_id>/', views.admin_delete_assignment, name='admin_delete_assignment'),

    # Admin o'quvchilar boshqaruvi
    path('admin-panel/students/', views.admin_students, name='admin_students'),
    path('admin-panel/students/assign-group/', views.admin_assign_student_group, name='admin_assign_student_group'),
    path('admin-panel/students/create-group/', views.admin_create_group, name='admin_create_group'),
    path('admin-panel/students/delete-group/<int:group_id>/', views.admin_delete_group, name='admin_delete_group'),
    # Admin fanlar (subjects) boshqaruvi
    path('admin-panel/subjects/', views.admin_subjects, name='admin_subjects'),
    path('admin-panel/subjects/create/', views.admin_create_subject, name='admin_create_subject'),
    path('admin-panel/subjects/edit/<int:subject_id>/', views.admin_edit_subject, name='admin_edit_subject'),
    path('admin-panel/subjects/delete/<int:subject_id>/', views.admin_delete_subject, name='admin_delete_subject'),
]
