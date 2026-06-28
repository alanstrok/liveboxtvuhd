# HomeKit bridge for the Orange Livebox TV UHD set-top box.
#
# HomeKit/mDNS needs the bridge to share the LAN, so run with host networking:
#   docker build -t liveboxtv-homekit -f homekit/Dockerfile .
#   docker run --rm -it --network host \
#       -e LIVEBOX_HOST=192.168.1.20 \
#       -v "$PWD/homekit-data:/data" \
#       liveboxtv-homekit
FROM python:3.11-slim

WORKDIR /app

# Build deps for HAP-python's cryptography wheels are usually prebuilt, but keep
# the image lean.
COPY homekit/requirements.txt homekit/requirements.txt
RUN pip install --no-cache-dir -r homekit/requirements.txt

# The bridge reads the channel lists from the integration, so copy both.
COPY custom_components/liveboxtvuhd/const_*.py custom_components/liveboxtvuhd/
COPY homekit/ homekit/

ENV LIVEBOX_COUNTRY=caraibe
VOLUME ["/data"]

ENTRYPOINT ["python", "-m", "homekit.run", "--persist-file", "/data/livebox.state"]
