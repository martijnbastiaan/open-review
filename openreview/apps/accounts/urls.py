from django.conf.urls import patterns, url
from openreview.apps.accounts.views import AuthenticationView, LogoutView, SettingsView, AccountDeleteView, ContributionsView

urlpatterns = patterns('',
    url('^login/$', AuthenticationView.as_view(), name="accounts-login"),
    url('^register/$', AuthenticationView.as_view(), name="accounts-register"),
    url('^logout/$', LogoutView.as_view(), name="accounts-logout"),
    url('^settings/$', SettingsView.as_view(), name="accounts-settings"),
    url('^contributions/$', ContributionsView.as_view(), name="accounts-contributions"),
    url('^delete/$', AccountDeleteView.as_view(), name="accounts-delete")
)
