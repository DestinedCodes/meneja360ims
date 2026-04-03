import os
import django
from django.contrib.auth import get_user_model

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'CyberPoa.settings')
django.setup()

User = get_user_model()
username = 'Mnjala' # <--- Put your admin username here
password = 'uchina@531' # <--- Put the password you want here

user, created = User.objects.get_or_create(username=username)
user.set_password(password)
user.is_superuser = True
user.is_staff = True
user.is_active = True

# Also bypass the "wait for approval" logic
if hasattr(user, 'is_approved'):
    user.is_approved = True

user.save()
print(f"✅ Account {username} has been updated/created and approved!")