#FROM mcr.microsoft.com/windows/servercore:ltsc2022
#SHELL ["powershell","-NoProfile","-ExecutionPolicy","Bypass","-Command"]
#
## Install Chocolatey and ensure source exists
#RUN Set-ExecutionPolicy Bypass -Scope Process -Force ; `
#    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 ; `
#    iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1')) ; `
#    choco feature enable -n=usePackageRepositoryOptimizations ; `
#    choco source add -n=chocolatey -s 'https://community.chocolatey.org/api/v2/' -y --priority=1
#
## Install Python + smartmontools (portable fallback), refresh PATH for THIS layer, verify
#RUN choco install -y python --no-progress ; `
#    try { choco install -y smartmontools --no-progress } catch { choco install -y smartmontools.portable --no-progress } ; `
#    [Environment]::SetEnvironmentVariable('Path', `
#      'C:\Program Files\Python311;C:\Program Files\Python311\Scripts;C:\Program Files\smartmontools\bin;C:\tools\smartmontools\bin;C:\ProgramData\chocolatey\bin;' + `
#      [Environment]::GetEnvironmentVariable('Path','Process'), 'Process') ; `
#    python --version ; `
#    smartctl --version
#
#ENV PATH="C:\\Program Files\\Python311;C:\\Program Files\\Python311\\Scripts;C:\\Program Files\\smartmontools\\bin;C:\\tools\\smartmontools\\bin;C:\\ProgramData\\chocolatey\\bin;%PATH%"
#
#WORKDIR /app
#
## Copy app
#COPY scripts /app/scripts
#COPY db /app/db
#COPY logs /app/logs
#COPY utils /app/utils
#COPY config /app/config
#COPY main.py /app/main.py
#COPY requirements.txt /app/requirements.txt
#COPY platform_infra/docker/healthcheck.py /app/healthcheck.py
#COPY platform_infra/docker/entrypoint.ps1 /app/entrypoint.ps1
#
## Install deps
#RUN python -m pip install --upgrade pip wheel setuptools ; \
#    pip install -r C:\app\requirements.txt ; \
#    pip install psutil
#
## Healthcheck + entrypoint
#HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
#  CMD ["powershell","-Command","try { python C:\\app\\healthcheck.py } catch { exit 1 }"]
#
#CMD ["powershell","-File","C:\\app\\entrypoint.ps1"]



#FROM mcr.microsoft.com/windows/servercore:ltsc2022
#SHELL ["powershell","-NoProfile","-ExecutionPolicy","Bypass","-Command"]
#
## 1) Install Chocolatey and ensure source exists
#RUN Set-ExecutionPolicy Bypass -Scope Process -Force ; [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 ; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1')) ; choco feature enable -n=usePackageRepositoryOptimizations ; choco source add -n=chocolatey -s 'https://community.chocolatey.org/api/v2/' -y --priority=1
#
## 2) Install Python + smartmontools (portable fallback). Refresh PATH for THIS layer and verify.
#RUN choco install -y python --no-progress ; try { choco install -y smartmontools --no-progress } catch { choco install -y smartmontools.portable --no-progress } ; [Environment]::SetEnvironmentVariable('Path','C:\Program Files\Python311;C:\Program Files\Python311\Scripts;C:\Program Files\smartmontools\bin;C:\tools\smartmontools\bin;C:\ProgramData\chocolatey\bin;' + [Environment]::GetEnvironmentVariable('Path','Process'),'Process') ; python --version ; smartctl --version
#
## 3) Persist PATH for later layers + runtime (Windows uses %PATH%)
#ENV PATH="C:\\Program Files\\Python311;C:\\Program Files\\Python311\\Scripts;C:\\Program Files\\smartmontools\\bin;C:\\tools\\smartmontools\\bin;C:\\ProgramData\\chocolatey\\bin;%PATH%"
#
## 4) Your app (copy whatever you already had)
#WORKDIR /app
#
#COPY scripts /app/scripts
#COPY db /app/db
#COPY logs /app/logs
#COPY utils /app/utils
#COPY config /app/config
#COPY requirements.txt /app/requirements.txt
#COPY main.py /app/main.py
#COPY platform_infra/docker/healthcheck.py /app/healthcheck.py
#COPY platform_infra/docker/entrypoint.ps1 /app/entrypoint.ps1
#
#RUN python -m pip install --upgrade pip wheel setuptools ; pip install -r C:\app\requirements.txt ; pip install psutil
#
#HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 CMD ["powershell","-Command","try { python C:\\app\\healthcheck.py } catch { exit 1 }"]
#CMD ["powershell","-File","C:\\app\\entrypoint.ps1"]







FROM mcr.microsoft.com/windows/servercore:ltsc2022
SHELL ["powershell","-NoProfile","-ExecutionPolicy","Bypass","-Command"]

# 1) Install Chocolatey
RUN Set-ExecutionPolicy Bypass -Scope Process -Force ; [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 ; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))

# 2) Install Python (latest from choco)
RUN choco install -y python --no-progress

# 3) Install smartmontools (portable avoids GUI installer)
RUN choco install -y smartmontools.portable --no-progress

# 4) Refresh PATH for THIS layer and verify tools
RUN if (Test-Path 'C:\Python314\python.exe') { $py='C:\Python314' } elseif (Test-Path 'C:\Python311\python.exe') { $py='C:\Python311' } else { throw 'Python not found after install' } ; $sm='C:\tools\smartmontools\bin' ; $env:Path = "$py;$py\Scripts;$sm;C:\ProgramData\chocolatey\bin;$env:Path" ; & "$py\python.exe" --version ; & "$sm\smartctl.exe" --version

# 5) Persist PATH for later layers & runtime
ENV PATH="C:\\Python314;C:\\Python314\\Scripts;C:\\Python311;C:\\Python311\\Scripts;C:\\tools\\smartmontools\\bin;C:\\ProgramData\\chocolatey\\bin;%PATH%"

# 6) App files (your existing POSIX-style paths are fine on Windows)
WORKDIR /app
COPY scripts /app/scripts
COPY db /app/db
COPY logs /app/logs
COPY utils /app/utils
COPY config /app/config
COPY requirements.txt /app/requirements.txt
COPY main.py /app/main.py
COPY platform_infra/docker/healthcheck.py /app/healthcheck.py
COPY platform_infra/docker/entrypoint.ps1 /app/entrypoint.ps1

# 7) Python deps
RUN python -m pip install --upgrade pip wheel setuptools ; pip install -r C:\app\requirements.txt ; pip install psutil

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 CMD ["powershell","-Command","try { python C:\\app\\healthcheck.py } catch { exit 1 }"]
CMD ["powershell","-File","C:\\app\\entrypoint.ps1"]




