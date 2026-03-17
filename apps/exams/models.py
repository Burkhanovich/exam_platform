from django.db import models
from django.conf import settings


class Subject(models.Model):
    """Fan (Subject) modeli"""
    name = models.CharField(max_length=200, verbose_name='Fan nomi')
    description = models.TextField(blank=True, verbose_name='Tavsif')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Yaratilgan vaqti')
    
    class Meta:
        verbose_name = 'Fan'
        verbose_name_plural = 'Fanlar'
        ordering = ['name']
    
    def __str__(self):
        return self.name


class Exam(models.Model):
    """Imtihon modeli"""
    
    EXAM_TYPES = (
        ('midterm', 'Oraliq nazorat'),
        ('final', 'Yakuniy nazorat'),
        ('practice', 'Mashq test'),
    )
    
    title = models.CharField(max_length=200, verbose_name='Imtihon nomi')
    subject = models.ForeignKey(
        Subject, 
        on_delete=models.CASCADE, 
        related_name='exams',
        verbose_name='Fan'
    )
    exam_type = models.CharField(
        max_length=20, 
        choices=EXAM_TYPES,
        verbose_name='Imtihon turi'
    )
    description = models.TextField(blank=True, verbose_name='Tavsif')
    duration = models.IntegerField(
        help_text='Davomiyligi (daqiqalarda)',
        verbose_name='Davomiyligi'
    )
    total_marks = models.IntegerField(
        default=100,
        verbose_name='Umumiy ball'
    )
    passing_marks = models.IntegerField(
        default=60,
        verbose_name='O\'tish balli'
    )
    start_time = models.DateTimeField(
        verbose_name='Boshlanish vaqti'
    )
    end_time = models.DateTimeField(
        verbose_name='Tugash vaqti'
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='Faol'
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='created_exams',
        verbose_name='Yaratuvchi'
    )
    allowed_groups = models.CharField(
        max_length=200,
        blank=True,
        help_text='Guruhlar (vergul bilan ajrating) — eski usul',
        verbose_name='Ruxsat etilgan guruhlar (eski)'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Yaratilgan vaqti'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Yangilangan vaqti'
    )
    
    class Meta:
        verbose_name = 'Imtihon'
        verbose_name_plural = 'Imtihonlar'
        ordering = ['-start_time']
    
    def __str__(self):
        return f"{self.title} - {self.subject.name}"
    
    def get_questions_count(self):
        """Imtihandagi savollar sonini qaytaradi"""
        return self.questions.count()
    
    def is_available(self):
        """Imtihon mavjudligini tekshiradi"""
        from django.utils import timezone
        now = timezone.now()
        return self.is_active and self.start_time <= now <= self.end_time


class ExamAssignment(models.Model):
    """Admin tomonidan o'qituvchiga fan+guruh biriktirilishi"""
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name='assignments',
        verbose_name='Fan'
    )
    group = models.ForeignKey(
        'users.StudentGroup',
        on_delete=models.CASCADE,
        related_name='assignments',
        verbose_name='Guruh'
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='assigned_exams',
        verbose_name='O\'qituvchi',
        limit_choices_to={'user_type': 'teacher'}
    )
    admin_start_time = models.DateTimeField(
        verbose_name='Ruxsat boshlanish vaqti',
        help_text='Admin belgilagan ruxsat boshlanish vaqti',
        null=True,
        blank=True,
    )
    admin_deadline = models.DateTimeField(
        verbose_name='Ruxsat tugash vaqti',
        help_text='Admin belgilagan oxirgi muddat'
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='exam_assignments_made',
        verbose_name='Biriktirgan admin'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Biriktirilgan vaqti'
    )

    def is_active_now(self):
        """Ruxsat hozir faolmi"""
        from django.utils import timezone
        now = timezone.now()
        start = self.admin_start_time or self.created_at
        return start <= now <= self.admin_deadline

    class Meta:
        verbose_name = 'Imtihon tayinlanishi'
        verbose_name_plural = 'Imtihon tayinlanishlari'
        unique_together = ['subject', 'group', 'teacher']
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.subject.name} → {self.group.name} → {self.teacher.get_full_name()}"


class ExamGroupPermission(models.Model):
    """O'qituvchi tomonidan guruhga imtihon ruxsati"""
    exam = models.ForeignKey(
        Exam,
        on_delete=models.CASCADE,
        related_name='group_permissions',
        verbose_name='Imtihon'
    )
    group = models.ForeignKey(
        'users.StudentGroup',
        on_delete=models.CASCADE,
        related_name='exam_permissions',
        verbose_name='Guruh'
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='given_permissions',
        verbose_name='Ruxsat bergan o\'qituvchi'
    )
    deadline = models.DateTimeField(
        verbose_name='Deadline',
        help_text='Guruh uchun oxirgi muddat'
    )
    duration = models.IntegerField(
        null=True,
        blank=True,
        verbose_name='Vaqt (daqiqa)',
        help_text='Guruh uchun test davomiyligi. Bo\'sh bo\'lsa imtihon davomiyligi ishlatiladi.'
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='Faol'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Ruxsat berilgan vaqti'
    )

    class Meta:
        verbose_name = 'Guruh ruxsati'
        verbose_name_plural = 'Guruh ruxsatlari'
        unique_together = ['exam', 'group']
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.exam.title} → {self.group.name} (deadline: {self.deadline})"

    def is_valid(self):
        """Ruxsat hali amal qilayotganini tekshiradi"""
        from django.utils import timezone
        return self.is_active and timezone.now() <= self.deadline


class ExamAttempt(models.Model):
    """Imtihon urinishi modeli"""
    
    STATUS_CHOICES = (
        ('in_progress', 'Jarayonda'),
        ('completed', 'Yakunlangan'),
        ('abandoned', 'Tashlab ketilgan'),
    )
    
    exam = models.ForeignKey(
        Exam,
        on_delete=models.CASCADE,
        related_name='attempts',
        verbose_name='Imtihon'
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='exam_attempts',
        verbose_name='Student'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='in_progress',
        verbose_name='Holat'
    )
    started_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Boshlangan vaqt'
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Yakunlangan vaqt'
    )
    
    class Meta:
        verbose_name = 'Imtihon urinishi'
        verbose_name_plural = 'Imtihon urinishlari'
        ordering = ['-started_at']
        unique_together = ['exam', 'student']
    
    def __str__(self):
        return f"{self.student.get_full_name()} - {self.exam.title}"
