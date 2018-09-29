from chainview_webserver import app as application

# Suggested apache2 config
# Outside virtual hosts:
#   WSGIDaemonProcess wsgi user=... group=... threads=3 home=/path-to-chainview-code python-path=/path-to-chainview-code
# Inside virtual host section:
#   WSGIScriptAlias / /path-to-chainview-code/apache2.wsgi
#   <Directory /path-to-chainview-code>
#        WSGIProcessGroup wsgi
#        WSGIApplicationGroup %{GLOBAL}
#        Order deny,allow
#        Allow from all
#   </Directory>

