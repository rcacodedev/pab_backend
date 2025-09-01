from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin

class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('El email es obligatorio')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save()
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password=password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    username=None
    email = models.EmailField(unique=True)
    nombre = models.CharField(max_length=100)
    primer_apellido = models.CharField(max_length=150)
    segundo_apellido = models.CharField(max_length=150, blank=True, null=True)
    direccion = models.CharField(max_length=200)
    dni = models.CharField(max_length=20)
    ciudad = models.CharField(max_length=50)
    pais = models.CharField(max_length=50)
    provincia = models.CharField(max_length=50)
    codigo_postal = models.CharField(max_length=10)
    phone = models.CharField(max_length=20)
    profile_image = models.ImageField(upload_to="profile_images/", blank=True, null=True)
    accepted_terms = models.BooleanField(default=False)
    accepted_terms_date = models.DateTimeField(null=True, blank=True)


    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['nombre', 'primer_apellido']

    class Meta:
        verbose_name = 'user'
        verbose_name_plural = 'users'

    # IMPORTANTE: evitar conflicto con auth.User
    groups = models.ManyToManyField(
        'auth.Group',
        related_name='accounts_users',
        blank=True,
        help_text='Grupos a los que pertenece el usuario.',
        verbose_name='grupos'
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        related_name='accounts_users_permissions',
        blank=True,
        help_text='Permisos específicos del usuario.',
        verbose_name='permisos de usuario'
    )

    def __str__(self):
        return self.email