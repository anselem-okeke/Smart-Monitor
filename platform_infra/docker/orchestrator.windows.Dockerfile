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


#1
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




##2
#FROM mcr.microsoft.com/windows/servercore:ltsc2022
#SHELL ["powershell","-NoProfile","-ExecutionPolicy","Bypass","-Command"]
#
## 1) Install Chocolatey (exec-form RUN on ONE line)
#RUN ["powershell","-NoProfile","-ExecutionPolicy","Bypass","-Command","Set-ExecutionPolicy Bypass -Scope Process -Force; [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1')); choco feature enable -n=usePackageRepositoryOptimizations"]
#
## 2) Install Python (pinned) and verify absolute path
#RUN ["powershell","-NoProfile","-ExecutionPolicy","Bypass","-Command","choco install -y python --version=3.11.9 --no-progress"]
#RUN ["powershell","-NoProfile","-ExecutionPolicy","Bypass","-Command","if (!(Test-Path 'C:\\Python311\\python.exe')) { throw 'Python not found at C:\\Python311\\python.exe' } ; & 'C:\\Python311\\python.exe' --version"]
#
## 3) Install smartmontools (portable → fixed path) and verify
#RUN ["powershell","-NoProfile","-ExecutionPolicy","Bypass","-Command","choco install -y smartmontools.portable --no-progress"]
#RUN ["powershell","-NoProfile","-ExecutionPolicy","Bypass","-Command","& 'C:\\tools\\smartmontools\\bin\\smartctl.exe' --version"]
#
## 4) Persist PATH
#ENV PATH="C:\\Python311;C:\\Python311\\Scripts;C:\\tools\\smartmontools\\bin;C:\\ProgramData\\chocolatey\\bin;%PATH%"
#
## 5) App payload (use forward slashes in Dockerfile paths)
#WORKDIR C:/app
#COPY scripts                        C:/app/scripts
#COPY db                             C:/app/db
#COPY logs                           C:/app/logs
#COPY utils                          C:/app/utils
#COPY config                         C:/app/config
#COPY requirements.txt               C:/app/requirements.txt
#COPY main.py                        C:/app/main.py
#COPY platform_infra/docker/healthcheck.py  C:/app/healthcheck.py
#COPY platform_infra/docker/entrypoint.ps1  C:/app/entrypoint.ps1
#
## 6) Python deps (absolute path)
#RUN ["powershell","-NoProfile","-ExecutionPolicy","Bypass","-Command","'C:\\Python311\\python.exe' -m pip install --upgrade pip wheel setuptools"]
#RUN ["powershell","-NoProfile","-ExecutionPolicy","Bypass","-Command","'C:\\Python311\\python.exe' -m pip install -r C:\\app\\requirements.txt"]
#RUN ["powershell","-NoProfile","-ExecutionPolicy","Bypass","-Command","'C:\\Python311\\python.exe' -m pip install psutil"]
#
## 7) Healthcheck + entrypoint
#HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 CMD ["powershell","-NoProfile","-Command","try { & 'C:\\Python311\\python.exe' 'C:\\app\\healthcheck.py' } catch { exit 1 }"]
#CMD ["powershell","-NoProfile","-File","C:\\app\\entrypoint.ps1"]



FROM mcr.microsoft.com/windows/servercore:ltsc2022
SHELL ["powershell","-NoProfile","-ExecutionPolicy","Bypass","-Command"]

# 1) Install Chocolatey
RUN ["powershell","-NoProfile","-ExecutionPolicy","Bypass","-Command","Set-ExecutionPolicy Bypass -Scope Process -Force; [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1')); choco feature enable -n=usePackageRepositoryOptimizations"]

# 2) Ensure the Chocolatey community source exists/enabled (some CI images override sources)
RUN ["powershell","-NoProfile","-ExecutionPolicy","Bypass","-Command","choco source remove -n=chocolatey -y *> $null; choco source add -n=chocolatey -s https://community.chocolatey.org/api/v2/ -y --priority=1; choco source enable -n=chocolatey"]

# 3) Install Python (pinned) and verify
RUN ["powershell","-NoProfile","-ExecutionPolicy","Bypass","-Command","choco install -y python --version=3.11.9 --no-progress"]
RUN ["powershell","-NoProfile","-ExecutionPolicy","Bypass","-Command","if (!(Test-Path 'C:\\Python311\\python.exe')) { throw 'Python not found at C:\\Python311\\python.exe' } ; & 'C:\\Python311\\python.exe' --version"]

# 4) Install smartmontools (non-portable MSI) and verify
RUN ["powershell","-NoProfile","-ExecutionPolicy","Bypass","-Command","choco install -y smartmontools --no-progress"]
RUN ["powershell","-NoProfile","-ExecutionPolicy","Bypass","-Command","& 'C:\\Program Files\\smartmontools\\bin\\smartctl.exe' --version"]

# 5) Persist PATH
ENV PATH="C:\\Python311;C:\\Python311\\Scripts;C:\\Program Files\\smartmontools\\bin;C:\\ProgramData\\chocolatey\\bin;%PATH%"

# 6) App payload
WORKDIR C:/app
COPY scripts                                  C:/app/scripts
COPY db                                       C:/app/db
COPY logs                                     C:/app/logs
COPY utils                                    C:/app/utils
COPY config                                   C:/app/config
COPY requirements.txt                          C:/app/requirements.txt
COPY main.py                                   C:/app/main.py
COPY platform_infra/docker/healthcheck.py      C:/app/healthcheck.py
COPY platform_infra/docker/entrypoint.ps1      C:/app/entrypoint.ps1

# 7) Python deps (absolute path)
#RUN ["powershell","-NoProfile","-ExecutionPolicy","Bypass","-Command","'C:\\Python311\\python.exe' -m pip install --upgrade pip wheel setuptools"]
#RUN ["powershell","-NoProfile","-ExecutionPolicy","Bypass","-Command","'C:\\Python311\\python.exe' -m pip install -r C:\\app\\requirements.txt"]
#RUN ["powershell","-NoProfile","-ExecutionPolicy","Bypass","-Command","'C:\\Python311\\python.exe' -m pip install psutil"]
RUN ["powershell","-NoProfile","-ExecutionPolicy","Bypass","-Command","C:\\Python311\\python.exe -m pip install --upgrade pip wheel setuptools"]
RUN ["powershell","-NoProfile","-ExecutionPolicy","Bypass","-Command","C:\\Python311\\python.exe -m pip install -r C:\\app\\requirements.txt"]
RUN ["powershell","-NoProfile","-ExecutionPolicy","Bypass","-Command","C:\\Python311\\python.exe -m pip install psutil"]


# 8) Healthcheck + entrypoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 CMD ["powershell","-NoProfile","-Command","try { & 'C:\\Python311\\python.exe' 'C:\\app\\healthcheck.py' } catch { exit 1 }"]
CMD ["powershell","-NoProfile","-File","C:\\app\\entrypoint.ps1"]








