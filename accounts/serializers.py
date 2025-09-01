# auth/serializers.py
import re
from django.utils import timezone
from rest_framework import serializers
from .models import User

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    password2 = serializers.CharField(write_only=True, label="Confirmar contraseña")
    accept_terms = serializers.BooleanField(write_only=True)

    class Meta:
        model = User
        fields = (
            'email', 'password', 'password2', 'accept_terms',
            'nombre', 'primer_apellido', 'segundo_apellido',
            'direccion', 'dni', 'ciudad', 'pais', 'provincia', 'codigo_postal',
            'phone', 'profile_image'
        )

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password": "Las contraseñas no coinciden."})

        if not attrs.get('accept_terms', False):
            raise serializers.ValidationError({"accept_terms": "Debes aceptar los términos y condiciones."})

        return attrs

    def validate_dni(self, value):
        if not re.match(r'^[A-Za-z0-9]{5,20}$', value):
            raise serializers.ValidationError("DNI inválido.")
        return value

    def validate_phone(self, value):
        if not re.match(r'^\+?\d{7,15}$', value):
            raise serializers.ValidationError("Teléfono inválido.")
        return value

    def create(self, validated_data):
        validated_data.pop('password2', None)
        accept_terms = validated_data.pop('accept_terms', False)
        profile_image = validated_data.pop('profile_image', None)

        user = User.objects.create_user(**validated_data)

        if profile_image:
            user.profile_image = profile_image

        if accept_terms:
            user.accepted_terms = True
            user.accepted_terms_date = timezone.now()

        user.save()
        return user


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = "__all__"

class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = (
            'email',
            'nombre', 'primer_apellido', 'segundo_apellido',
            'direccion', 'dni', 'ciudad', 'pais', 'provincia',
            'codigo_postal', 'phone', 'profile_image'
        )

    def validate_profile_image(self, value):
        # Validar tamaño máximo 2MB
        if value.size > 2 * 1024 * 1024:
            raise serializers.ValidationError("La imagen es demasiado grande (máx 2MB).")
        # Validar tipo de archivo
        if not value.content_type.startswith("image/"):
            raise serializers.ValidationError("El archivo debe ser una imagen.")
        return value

    def validate_dni(self, value):
        import re
        if not re.match(r'^[A-Za-z0-9]{5,20}$', value):
            raise serializers.ValidationError("DNI inválido.")
        return value

    def validate_phone(self, value):
        import re
        if not re.match(r'^\+?\d{7,15}$', value):
            raise serializers.ValidationError("Teléfono inválido.")
        return value