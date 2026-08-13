# SPDX-License-Identifier: MPL-2.0

FROM arm32v7/debian:bullseye-slim

RUN apt-get update -qq \
 && apt-get install -y -qq --no-install-recommends gcc libc6-dev \
 && rm -rf /var/lib/apt/lists/*

COPY fbshim.c /opt/rx3emu/fbshim.c
COPY run.sh /opt/rx3emu/run.sh

RUN gcc -shared -fPIC -O2 -Wall -Wextra \
      -o /opt/rx3emu/fbshim.so /opt/rx3emu/fbshim.c -ldl \
 && chmod 755 /opt/rx3emu/run.sh

ENTRYPOINT ["/opt/rx3emu/run.sh"]
