***********
printer-gui
***********

| Django web app for RPi to handle print jobs using a connected CUPS printer.

.. image:: ./screenshots/preview.png
    :width: 800
    :alt: Printer-GUI's desktop and mobile views

Highlights
##########

- Per-session print queues keep simultaneous users from seeing or deleting
  each other's jobs and automatically clean up uploaded files after
  printing.
- Docuvert-powered conversion renders Microsoft Office, OpenDocument, and RTF
  uploads to PDF while allowing CUPS-native formats to print directly.
- Django's Messages Framework surfaces ``lp`` output, conversion problems, and
  other errors directly in the browser.
- The printer diagnostics dashboard summarises IPP state, printer messages, and
  supply levels using ``ipptool`` when available and falling back to
  ``pycups``/``lpstat`` when the CLI tool is not present.
- Startup helpers refresh static assets, capture subprocess ``stderr``, and
  offer a one-command Gunicorn launcher for Raspberry Pi deployments.
- Automatic migrations, hostname discovery, and sanitised upload filenames
  reduce manual setup effort on a single-board computer.


Requirements
############

- Raspberry Pi or similar SBC with networking capability
- Python 3.10+ (required by Django 5.2) and the ``pip`` package installer on the SBC's OS.
- Ability to install CUPS so the ``lp``, ``lpstat``, and ``ipptool`` commands are
  available to the application.
- A network printer connected on the local network
- Docuvert 1.1.2 (``pip install docuvert==1.1.2``) to convert Office documents
  and OpenDocument files to PDF before printing
- (Optional) ``pycups`` to enhance the diagnostics view. The app falls back to
  command-line tools when the module is not installed.


Limitations
###########
- Formats beyond pdf, ps, txt, jpg, jpeg, png, gif, tif/tiff, doc/docx,
  ppt/pptx, xls/xlsx, odt/odp/ods, and rtf remain unsupported.
- It seems that some printers may not respect page orientation chosen.


Setup
#####

| Follow the steps below to convert your single-board computer
| into a printer server on your local network.


1) Connect your printer via CUPS
--------------------------------
| On your single-board computer, you will first need to connect
| to your printer using CUPS. I was not in the mood for reading
| command-line documentation and was able to set this up in a
| few minutes using the CUPS web GUI. There are many tutorials
| on how to do this such as `this one <https://www.howtogeek.com/169679/how-to-add-a-printer-to-your-raspberry-pi-or-other-linux-computer/>`_.


2) Install system packages
--------------------------
| Install the CUPS packages so the ``lp``, ``lpstat``, and ``ipptool`` commands
| are available to Django. LibreOffice remains unnecessary; Docuvert
| (installed via ``pip``) now
| handles Office/OpenDocument conversions. On Debian/Ubuntu:

.. code:: bash

    sudo apt update
    sudo apt install cups
    sudo usermod -aG lpadmin $USER
    sudo systemctl enable --now cups

| On other distributions, install the package that provides the ``lp`` and
| ``lpstat`` utilities (often named ``cups`` or ``cups-client``) and ensure
| the ``ipptool`` command is available. Installing ``pycups`` alongside the
| project is optional but enables richer diagnostics when available.


3) Download the project files
-----------------------------
| Move the application's source code onto the single-board computer before
| continuing. If ``git`` is available, cloning your fork of the repository
| keeps it easy to pull in future updates:

.. code:: bash

    cd /opt
    git clone https://github.com/JPWTCK/printer-gui.git
    cd printer-gui

| You can also transfer the project directory from another machine with
| ``scp``, ``rsync``, or a USB drive. The remaining steps assume commands are
| run from the project's root directory on the SBC.


4) Setup the virtualenv
-----------------------
| The ``printergui.bash`` helper now handles almost all of the initial
| configuration for you. Running it from the project root will create the
| ``venv`` directory if needed, install dependencies (unless
| ``PRINTER_GUI_SKIP_REQUIREMENTS=1``), refresh static assets, and start
| Gunicorn with sensible defaults:

.. code:: bash

    ./printergui.bash

| Export ``PRINTER_GUI_BIND_ADDRESS`` or ``PRINTER_GUI_GUNICORN_WORKERS``
| before launching the helper to customise its runtime settings. The
| separate ``install-service.bash`` script only installs the optional
| systemd unit when you want the service to run on boot.

| If you prefer to manage the environment yourself, create the virtualenv
| in the project root, activate it, install the requirements, and build the
| static asset manifest manually:

.. code:: bash

    python3 -m venv venv
    source venv/bin/activate
    pip3 install -r requirements.txt
    python manage.py collectstatic --no-input


5) Database initialization (automatic)
--------------------------------------
| The application now ships with its database migrations and applies them
| automatically the first time the server starts, so there is no separate
| setup step to run.
|
| If you prefer to manage the database manually you can still apply the
| migrations yourself:

.. code:: bash

    python manage.py migrate

| Set the ``PRINTER_GUI_AUTO_APPLY_MIGRATIONS`` environment variable to ``0``
| to opt out of the automatic migration behavior when needed.

6) Locate your device on the network (optional)
-----------------------------------------------
| The application automatically adds any hostnames and IP addresses that
| belong to the machine to Django's ``ALLOWED_HOSTS`` list. On Raspberry
| Pi OS and many other Linux distributions, you can usually reach the
| device with ``http://<HOSTNAME>.local:8000`` immediately. Assigning a
| static IP address is no longer required, though you can still set one if
| you prefer a predictable address.


7) Start the Gunicorn application server
---------------------------------------
| If you used ``printergui.bash`` in the previous step, Gunicorn is already
| running with the helper's defaults. To manage the server manually, activate
| the virtualenv and start Gunicorn using the bundled WSGI entry point.
| Adjust the worker count for your hardware (two workers are a good starting
| point for a Raspberry Pi 4):

.. code:: bash

    source venv/bin/activate
    gunicorn --workers 2 --bind 0.0.0.0:8000 printer.wsgi:application

| After Gunicorn starts, visit the site in a browser and make sure the UI is
| styled. You can also request a known static asset directly to confirm
| WhiteNoise is serving the collected files:

.. code:: bash

    curl -I http://<HOSTNAME>.local:8000/static/css/style.css

| Re-run ``./printergui.bash`` whenever you want the helper to restart the
| service—it keeps the virtualenv in place, reinstalls dependencies when
| needed (unless ``PRINTER_GUI_SKIP_REQUIREMENTS=1``), refreshes static assets,
| and then launches Gunicorn for you.

| For local development with automatic reloads you can still run
| ``python manage.py runserver``, but prefer Gunicorn (or another
| production-grade server) for network-accessible deployments.


| Assuming the server runs correctly, you may configure the
| server to run automatically on startup as a systemd service.
| On the Raspberry Pi, copy the 'printergui.service' file
| to '/etc/systemd/system/', review the ``User``, ``Group``,
| ``WorkingDirectory``, and ``ExecStart`` directives, and adjust
| them if your environment differs from the defaults. The service reads
| optional overrides from ``/etc/default/printergui``; you can
| define ``PRINTER_GUI_BIND_ADDRESS`` there to change the bind
| address, ``PRINTER_GUI_GUNICORN_WORKERS`` to tune the worker
| count, and ``PRINTER_GUI_ALLOWED_HOSTS`` to permit additional
| hostnames without editing the unit file. For example:

.. code:: bash

    echo "PRINTER_GUI_BIND_ADDRESS=192.168.1.4:8000" | sudo tee /etc/default/printergui
    echo "PRINTER_GUI_GUNICORN_WORKERS=3" | sudo tee -a /etc/default/printergui
    echo "PRINTER_GUI_ALLOWED_HOSTS=printer.example.com,printer.local" | sudo tee -a /etc/default/printergui

| The unit invokes ``printergui.bash`` so each restart refreshes the static assets
| automatically before Gunicorn launches. If you customize the unit to call
| Gunicorn directly, keep a ``collectstatic`` step in your workflow.

| Start and enable it once it matches your setup. The repository includes a helper
| script to copy the unit file into place, reload systemd, and optionally enable
| and start the service:

.. code:: bash

    cd /home/pi/printer-gui
    sudo ./install-service.bash --enable --start

| By default the script installs ``printergui.service`` to
| ``/etc/systemd/system``. Use ``--service-file`` or ``--target-dir`` to point to
| custom locations, and pass ``--enable`` and ``--start`` (or ``--now``) only when
| you are ready for the service to run automatically. If you prefer to execute
| the steps manually, run:

.. code:: bash

    sudo cp /home/pi/printer-gui/printergui.service /etc/systemd/system/
    sudo systemctl start printergui
    sudo systemctl enable printergui


| To check the status of the service and debug, use:
|
| ``systemctl status printergui``, and
| ``sudo journalctl -u printergui``

8) Configure the server to use your printer
-------------------------------------------
| The printer server has not yet been configured to use your
| CUPS printer profile. With the server running, visit its
| URL in a web browser from a device on the same network
| (e.g. http://<HOSTNAME>.local:8000). Locate and click the
| settings icon as pictured below:

.. image:: screenshots/configure-printer.png
    :width: 800
    :alt: Configuring printer profile


| As you can see in the picture, you can also set a title and
| defaults for the print server. Now the server should be able
| to print correctly. Upload some test files, configure the
| options, and print out the files if you wish.

9) Review printer diagnostics (optional)
---------------------------------------
| Use the navigation bar's status link (``/status/``) to open the diagnostics
| dashboard. The view queries ``ipptool`` for IPP attributes, falls back to
| ``pycups`` when available, and ultimately ``lpstat`` to display the printer's
| current state, any reported error messages, and supply levels. Refresh the
| page whenever you need to confirm the printer is online before starting a
| print batch.


Using the web interface
#######################

* **Uploading files:** the upload form accepts the formats listed in
  ``printer/upload_types.py``. Filenames are sanitised before saving and files
  live in ``static/uploads`` until they are deleted or printed. Non-PDF uploads
  are rendered to PDF automatically via Docuvert.
* **Managing the queue:** each browser session has its own queue. Use the edit
  dialog to adjust page ranges, colour mode, and orientation before printing.
  Defaults come from the Settings page so administrators can preselect sensible
  values for their printer.
* **Printing jobs:** starting a print run calls ``lp`` for every queued file,
  surfaces any ``stderr`` output as on-screen alerts, and removes jobs as they
  succeed. If a job fails it remains visible so you can retry after addressing
  the issue.
* **Monitoring the printer:** the diagnostics page and the printer status badge
  on the home screen provide quick visibility into the device's state and any
  reported warnings.


Environment variables
#####################

- ``DJANGO_SECRET_KEY`` – supply a persistent secret key in production
  environments instead of allowing Django to generate one at runtime.
- ``PRINTER_GUI_BIND_ADDRESS`` – set the host and port Gunicorn should bind to
  (defaults to ``0.0.0.0:8000``).
- ``PRINTER_GUI_GUNICORN_WORKERS`` – control the number of Gunicorn workers.
- ``PRINTER_GUI_ALLOWED_HOSTS`` – provide additional comma-separated hostnames
  that should be added to Django's ``ALLOWED_HOSTS`` list.
- ``PRINTER_GUI_SKIP_REQUIREMENTS`` – set to ``1`` to stop
  ``printergui.bash`` from running ``pip install -r requirements.txt``.
- ``PRINTER_GUI_AUTO_APPLY_MIGRATIONS`` – set to ``0`` to disable automatic
  migration execution at startup.
