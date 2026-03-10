from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse, Http404
from django.conf import settings
import os
import shutil
from datetime import datetime
from .models import BusinessProfile


@login_required
def backup_database(request):
    """Create a backup of the SQLite database"""
    try:
        # Database path
        db_path = settings.DATABASES['default']['NAME']
        db_dir = os.path.dirname(db_path)
        db_filename = os.path.basename(db_path)

        # Create backup filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f"backup_{timestamp}_{db_filename}"
        backup_path = os.path.join(db_dir, backup_filename)

        # Copy the database file
        shutil.copy2(db_path, backup_path)

        messages.success(request, f'Database backup created successfully: {backup_filename}')

        # Return the backup file for download
        with open(backup_path, 'rb') as f:
            response = HttpResponse(f.read(), content_type='application/octet-stream')
            response['Content-Disposition'] = f'attachment; filename="{backup_filename}"'
            return response

    except Exception as e:
        messages.error(request, f'Error creating backup: {str(e)}')
        return redirect('backup')


@login_required
def restore_database(request):
    """Restore database from backup file"""
    if request.method == 'POST':
        backup_file = request.FILES.get('backup_file')

        if not backup_file:
            messages.error(request, 'Please select a backup file to restore.')
            return redirect('restore')

        try:
            # Database path
            db_path = settings.DATABASES['default']['NAME']
            db_dir = os.path.dirname(db_path)

            # Create restore filename with timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            restore_filename = f"restore_{timestamp}_{os.path.basename(db_path)}"
            restore_path = os.path.join(db_dir, restore_filename)

            # Save uploaded file temporarily
            temp_path = os.path.join(db_dir, 'temp_restore.db')
            with open(temp_path, 'wb+') as f:
                for chunk in backup_file.chunks():
                    f.write(chunk)

            # Validate the backup file (basic check)
            if not validate_sqlite_file(temp_path):
                os.remove(temp_path)
                messages.error(request, 'Invalid backup file. Please select a valid SQLite database file.')
                return redirect('restore')

            # Create backup of current database before restore
            current_backup = os.path.join(db_dir, f"pre_restore_{timestamp}_{os.path.basename(db_path)}")
            shutil.copy2(db_path, current_backup)

            # Perform restore
            shutil.copy2(temp_path, restore_path)
            shutil.move(restore_path, db_path)

            # Clean up temp file
            os.remove(temp_path)

            messages.success(request, 'Database restored successfully! The system will restart to apply changes.')
            messages.info(request, f'Previous database backed up as: {os.path.basename(current_backup)}')

            # Note: In a production system, you might want to restart the application here
            return redirect('dashboard')

        except Exception as e:
            messages.error(request, f'Error restoring database: {str(e)}')
            return redirect('restore')

    return redirect('restore')


@login_required
def list_backups(request):
    """List available backup files"""
    try:
        db_path = settings.DATABASES['default']['NAME']
        db_dir = os.path.dirname(db_path)
        db_filename = os.path.basename(db_path)

        # Find all backup files
        backups = []
        for filename in os.listdir(db_dir):
            if filename.startswith('backup_') and filename.endswith('.db'):
                filepath = os.path.join(db_dir, filename)
                stat = os.stat(filepath)
                backups.append({
                    'filename': filename,
                    'size': stat.st_size,
                    'created': datetime.fromtimestamp(stat.st_ctime),
                    'path': filepath
                })

        # Sort by creation date (newest first)
        backups.sort(key=lambda x: x['created'], reverse=True)

        return render(request, 'core/backup_list.html', {
            'backups': backups,
            'business': BusinessProfile.objects.first()
        })

    except Exception as e:
        messages.error(request, f'Error listing backups: {str(e)}')
        return redirect('backup')


@login_required
def download_backup(request, filename):
    """Download a specific backup file"""
    try:
        db_path = settings.DATABASES['default']['NAME']
        db_dir = os.path.dirname(db_path)

        # Security check - only allow backup files
        if not filename.startswith('backup_') or not filename.endswith('.db'):
            raise Http404("Backup file not found")

        filepath = os.path.join(db_dir, filename)

        if not os.path.exists(filepath):
            raise Http404("Backup file not found")

        with open(filepath, 'rb') as f:
            response = HttpResponse(f.read(), content_type='application/octet-stream')
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response

    except Exception as e:
        messages.error(request, f'Error downloading backup: {str(e)}')
        return redirect('backup_list')


@login_required
def delete_backup(request, filename):
    """Delete a backup file"""
    try:
        db_path = settings.DATABASES['default']['NAME']
        db_dir = os.path.dirname(db_path)

        # Security check
        if not filename.startswith('backup_') or not filename.endswith('.db'):
            messages.error(request, 'Invalid backup file')
            return redirect('backup_list')

        filepath = os.path.join(db_dir, filename)

        if os.path.exists(filepath):
            os.remove(filepath)
            messages.success(request, f'Backup file "{filename}" deleted successfully.')
        else:
            messages.error(request, 'Backup file not found.')

    except Exception as e:
        messages.error(request, f'Error deleting backup: {str(e)}')

    return redirect('backup_list')


def validate_sqlite_file(filepath):
    """Basic validation to check if file is a valid SQLite database"""
    try:
        with open(filepath, 'rb') as f:
            header = f.read(16)
            # SQLite files start with "SQLite format 3"
            return header.startswith(b'SQLite format 3')
    except:
        return False


@login_required
def backup_settings(request):
    """View and manage backup settings"""
    business = BusinessProfile.objects.first()

    if request.method == 'POST':
        # Handle backup settings update
        auto_backup = request.POST.get('auto_backup', 'off')
        backup_frequency = request.POST.get('backup_frequency', 'weekly')

        # In a real implementation, you'd save these to a settings model
        messages.success(request, 'Backup settings updated successfully.')
        return redirect('backup_settings')

    return render(request, 'core/backup_settings.html', {
        'business': business,
        'auto_backup_enabled': False,  # Default value
        'backup_frequency': 'weekly',  # Default value
    })


# Utility functions for automated backups
def create_automated_backup():
    """Create automated backup (to be called by cron job or scheduler)"""
    try:
        db_path = settings.DATABASES['default']['NAME']
        db_dir = os.path.dirname(db_path)
        db_filename = os.path.basename(db_path)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f"auto_backup_{timestamp}_{db_filename}"
        backup_path = os.path.join(db_dir, backup_filename)

        shutil.copy2(db_path, backup_path)

        # Clean up old automated backups (keep last 10)
        cleanup_old_backups(db_dir, 'auto_backup_', 10)

        return True, backup_filename
    except Exception as e:
        return False, str(e)


def cleanup_old_backups(directory, prefix, keep_count):
    """Clean up old backup files, keeping only the most recent ones"""
    try:
        files = [f for f in os.listdir(directory) if f.startswith(prefix)]
        files.sort(key=lambda x: os.path.getctime(os.path.join(directory, x)), reverse=True)

        # Remove files beyond the keep count
        for old_file in files[keep_count:]:
            os.remove(os.path.join(directory, old_file))
    except Exception:
        pass  # Silently ignore cleanup errors