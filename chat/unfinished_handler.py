from .models import UnfinishedReport
from django.http import JsonResponse
import json
from datetime import datetime, timedelta

class UnfinishedReportHandler:
    @staticmethod
    def save_unfinished_report(session_id, report_data):
        UnfinishedReport.objects.update_or_create(
            session_id=session_id,
            defaults={'report_data': report_data}
        )

    @staticmethod
    def get_unfinished_report(session_id):
        try:
            report = UnfinishedReport.objects.get(session_id=session_id)
            return report.get_report_data()
        except UnfinishedReport.DoesNotExist:
            return None

    @staticmethod
    def delete_unfinished_report(session_id):
        UnfinishedReport.objects.filter(session_id=session_id).delete()

    @staticmethod
    def clean_old_reports(days=7):
        cutoff_date = datetime.now() - timedelta(days=days)
        UnfinishedReport.objects.filter(last_updated__lt=cutoff_date).delete()

    @staticmethod
    def get_all_unfinished_reports():
        """Get all unfinished reports with their session IDs and last updated times"""
        reports = UnfinishedReport.objects.all().order_by('-last_updated')
        return [{
            'session_id': report.session_id,
            'report_data': report.report_data,
            'last_updated': report.last_updated.isoformat()
        } for report in reports]