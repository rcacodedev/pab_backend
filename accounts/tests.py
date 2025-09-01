# accounts/tests.py
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from .models import User
from django.core.files.uploadedfile import SimpleUploadedFile
import io
from PIL import Image

class AccountsFullTests(APITestCase):

    def setUp(self):
        # Usuario inicial para login y perfil
        self.user = User.objects.create_user(
            email="testuser@example.com",
            password="TestPassword123",
            nombre="Test",
            primer_apellido="User"
        )

    # -------------------
    # Registro
    # -------------------
    def test_register_user_success(self):
        url = reverse('register')
        data = {
            "email": "newuser@example.com",
            "password": "NewPass123",
            "password2": "NewPass123",
            "accept_terms": True,
            "nombre": "New",
            "primer_apellido": "User",
            "segundo_apellido": "Example",
            "direccion": "Calle Falsa 123",
            "dni": "ABC12345",
            "ciudad": "Madrid",
            "pais": "España",
            "provincia": "Madrid",
            "codigo_postal": "28001",
            "phone": "+34123456789"
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_register_password_mismatch(self):
        url = reverse('register')
        data = {
            "email": "user2@example.com",
            "password": "pass1",
            "password2": "pass2",
            "accept_terms": True,
            "nombre": "Mismatch",
            "primer_apellido": "Test",
            "dni": "ABC12345",
            "phone": "+34123456789"
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_without_accept_terms(self):
        url = reverse('register')
        data = {
            "email": "user3@example.com",
            "password": "pass123",
            "password2": "pass123",
            "accept_terms": False,
            "nombre": "NoTerms",
            "primer_apellido": "Test",
            "dni": "ABC12345",
            "phone": "+34123456789"
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_invalid_dni(self):
        url = reverse('register')
        data = {
            "email": "user4@example.com",
            "password": "pass123",
            "password2": "pass123",
            "accept_terms": True,
            "nombre": "BadDNI",
            "primer_apellido": "Test",
            "dni": "##BAD##",
            "phone": "+34123456789"
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_invalid_phone(self):
        url = reverse('register')
        data = {
            "email": "user5@example.com",
            "password": "pass123",
            "password2": "pass123",
            "accept_terms": True,
            "nombre": "BadPhone",
            "primer_apellido": "Test",
            "dni": "ABC12345",
            "phone": "123abc"
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # -------------------
    # Login con JWT
    # -------------------
    def get_token(self, email, password):
        url = reverse('login')
        response = self.client.post(url, {"email": email, "password": password}, format='json')
        return response.data.get('access', None)

    def test_login_success(self):
        url = reverse('login')
        data = {"email": "testuser@example.com", "password": "TestPassword123"}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_login_wrong_password(self):
        url = reverse('login')
        data = {"email": "testuser@example.com", "password": "WrongPass"}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, 400)

    def test_login_nonexistent_user(self):
        url = reverse('login')
        data = {"email": "nouser@example.com", "password": "pass123"}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, 400)

    # -------------------
    # Refresh token
    # -------------------
    def test_refresh_token(self):
        login_url = reverse('login')
        refresh_url = reverse('token_refresh')
        login_resp = self.client.post(login_url, {"email": "testuser@example.com", "password": "TestPassword123"}, format='json')
        refresh_token = login_resp.data['refresh']
        response = self.client.post(refresh_url, {"refresh": refresh_token}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)

    # -------------------
    # Vista protegida con JWT
    # -------------------
    def test_protected_view_requires_auth(self):
        url = reverse('protected')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_protected_view_with_token(self):
        url = reverse('protected')
        token = self.get_token("testuser@example.com", "TestPassword123")
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['user']['email'], "testuser@example.com")

    # -------------------
    # Perfil
    # -------------------
    def test_profile_get(self):
        url = reverse('profile')
        token = self.get_token("testuser@example.com", "TestPassword123")
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], self.user.email)

    def test_profile_patch_update(self):
        url = reverse('profile')
        token = self.get_token("testuser@example.com", "TestPassword123")
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

        # Creamos imagen válida en memoria
        img = io.BytesIO()
        image = Image.new('RGB', (100, 100), color='red')
        image.save(img, format='JPEG')
        img.seek(0)
        uploaded = SimpleUploadedFile("test.jpg", img.read(), content_type="image/jpeg")

        data = {"nombre": "UpdatedName", "profile_image": uploaded}
        response = self.client.patch(url, data, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["nombre"], "UpdatedName")
        self.assertTrue("profile_image" in response.data)

    def test_profile_patch_invalid_image(self):
        url = reverse('profile')
        token = self.get_token("testuser@example.com", "TestPassword123")
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

        uploaded = SimpleUploadedFile("test.txt", b"notanimage", content_type="text/plain")
        data = {"profile_image": uploaded}
        response = self.client.patch(url, data, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # -------------------
    # Logout (simulado)
    # -------------------
    def test_logout(self):
        # Aquí simulamos que el logout en frontend elimina token
        token = self.get_token("testuser@example.com", "TestPassword123")
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

        # Logout real no hay en backend si usas JWT sin blacklist
        # Solo verificamos que tras eliminar token ya no se puede acceder
        self.client.credentials()  # eliminamos headers
        response = self.client.get(reverse('protected'))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
