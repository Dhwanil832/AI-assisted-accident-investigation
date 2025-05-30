from django.urls import path
from .views import chatbot_api, chatbot_ui, upload_files, delete_file, user_dashboard, admin_dashboard, resume_existing_report, delete_unfinished_report


urlpatterns = [
    path("", chatbot_ui, name="chat_ui"),  
    path("api/chat/", chatbot_api, name="chatbot_api"),  
    path("upload_files/", upload_files, name="upload_files"),
    path("delete_file/", delete_file, name="delete_file"),
    path("dashboard/user/", user_dashboard, name="user_dashboard"),
    path("dashboard/admin/", admin_dashboard, name="admin_dashboard"),
    path("resume/<str:session_id>/", resume_existing_report, name="resume_report"),
    path("delete/<str:session_id>/", delete_unfinished_report, name="delete_report"),

]
