from django.db import models
import json

class IncidentReport(models.Model):
    report_json = models.JSONField()  # Store the full report as JSON
    created_at = models.DateTimeField(auto_now_add=True)
    creator_name       = models.CharField(max_length=100)
    creator_job_title  = models.CharField(max_length=100)
    last_modified_name = models.CharField(max_length=100, blank=True)
    last_modified_job  = models.CharField(max_length=100, blank=True)
    created_at         = models.DateTimeField(auto_now_add=True)
    last_modified_at   = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Report on {self.report_json.get('date', 'Unknown Date')} at {self.report_json.get('location', 'Unknown Location')}"



class UnfinishedReport(models.Model):
    session_id = models.CharField(max_length=100)
    report_data = models.JSONField()
    last_updated = models.DateTimeField(auto_now=True)
    
    def get_report_data(self):
        return self.report_data
    
    def set_report_data(self, data):
        self.report_data = data
        self.save()

class UploadedFile(models.Model):
    file = models.FileField(upload_to='uploads/%Y/%m/%d/')
    original_name = models.CharField(max_length=255)
    file_type = models.CharField(max_length=100)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    session_id = models.CharField(max_length=100)
    incident_report = models.ForeignKey('IncidentReport', on_delete=models.CASCADE, null=True, blank=True, related_name='attachments')
    is_temp = models.BooleanField(default=True)  # True for files uploaded during report creation, False for files attached to completed reports
    
    def __str__(self):
        return self.original_name