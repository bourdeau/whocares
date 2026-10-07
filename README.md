# FastAPI benchmark with Traefik

## Config

**Host:** `AMD Ryzen 7 9700X (8C/16T) · 30 GiB RAM · NixOS 26.05 (Linux 6.18.54) · Docker 29.8.1`

**App:** `python:3.14-slim` · FastAPI `0.142` · uvicorn `0.54[standard]` (uvloop + httptools) · `--workers 8` (1 per physical core) · `--no-access-log --no-server-header` · Traefik `v3.7`

| Host port | Path           | Purpose                                      |
| --------- | -------------- | -------------------------------------------- |
| `80`      | Traefik → API  | via Traefik (requires `Host: api.localhost`) |
| `8000`    | uvicorn direct | bypass Traefik                               |

## Quick RPS results — No CPU limit

`ab -n 80000 -c 100`

| Path                          | RPS    |
| ----------------------------- | ------ |
| Via Traefik (`localhost:80`)  | 34,928 |
| Direct (`localhost:8000`)     | 34,190 |
| Direct, container IP (no NAT) | 43,472 |

> `localhost:8000` is capped by Docker's port-forwarding NAT, so it lands near Traefik. The true uvicorn ceiling is measured via the container's network IP.

## Quick RPS results — 4 CPU limit

Both containers capped at `cpus: "4.0"`, uvicorn `--workers 4` (1 per core). Same `ab -n 80000 -c 100`.

| Path                          | RPS    |
| ----------------------------- | ------ |
| Via Traefik (`localhost:80`)  | 31,314 |
| Direct (`localhost:8000`)     | 26,169 |
| Direct, container IP (no NAT) | 34,602 |

## Quick RPS results — 2 CPU limit

Both containers capped at `cpus: "2.0"`, uvicorn `--workers 2` (1 per core). Same `ab -n 80000 -c 100`.

| Path                          | RPS    |
| ----------------------------- | ------ |
| Via Traefik (`localhost:80`)  | 21,591 |
| Direct (`localhost:8000`)     | 17,323 |
| Direct, container IP (no NAT) | 19,414 |

## Quick RPS results — 1 CPU limit

Both containers capped at `cpus: "1.0"`, uvicorn `--workers 1`. Same `ab -n 80000 -c 100`.

| Path                          | RPS    |
| ----------------------------- | ------ |
| Via Traefik (`localhost:80`)  | 12,700 |
| Direct (`localhost:8000`)     | 9,163  |
| Direct, container IP (no NAT) | 9,902  |

### Why "via Traefik" can beat "direct"

Direct hits force the single Python worker to spend its one CPU on connection handling (`accept`/epoll/socket I/O across 100 connections). Traefik offloads that to its own container and keeps a persistent keep-alive pool to the backend, so uvicorn just parses/responds. The api is CPU-bound either way (~93%), just doing more useful work behind the proxy.

## Upload endpoint results

`POST /upload` accepts a raw `application/octet-stream` body and writes it to disk (`/tmp/uploads/<uuid>.bin`, via `aiofiles`). Benchmarked with a random 1 KB payload using the same scenarios as the `GET /` runs above:

```sh
head -c 1024 /dev/urandom > random1k.bin
ab -n 80000 -c 100 -p random1k.bin -T application/octet-stream <url>/upload
# via Traefik, add: -H "Host: api.localhost"
```

| Scenario                | Via Traefik (`localhost:80`) | Direct (`localhost:8000`) | Direct, container IP (no NAT) |
| ----------------------- | ---------------------------- | ------------------------- | ----------------------------- |
| No CPU limit, 8 workers | 21,494                       | 20,524                    | 23,498                        |
| 4 CPU limit, 4 workers  | 14,747                       | 12,587                    | 14,727                        |
| 2 CPU limit, 2 workers  | 10,168                       | 8,293                     | 9,584                         |
| 1 CPU limit, 1 worker   | 6,269                        | 4,974                     | 5,452                         |

Each request writes a distinct file on disk, so this route is disk-I/O bound rather than CPU bound — hence throughput well below the `GET /` numbers, and it scales up roughly with worker/core count rather than hitting the CPU ceiling.

## ulimit (`nofile`) findings

Both containers start with Docker's default soft `nofile` limit of **1024** (hard `524288`). Raising the soft limit to `524288` (via `ulimits.nofile` in `docker-compose.yml`) makes **no difference at the benchmark parameters above** — at `-c 100` a worker only holds ~100 sockets plus the file being written, far below 1024.

| ulimit      | `-c 100` (no keep-alive, 8 workers) | `-k -c 2000` (1 worker)                |
| ----------- | ----------------------------------- | -------------------------------------- |
| soft 1024   | 22,231 / 20,304 / 23,470 RPS        | `Connection reset by peer` (ab aborts) |
| soft 524288 | 22,087 / 20,314 / 23,496 RPS        | 0 failures, ~6,000 RPS                 |

The limit is real but only bites under persistent connections and high concurrency: with `-k -c 2000` a single worker needs ~2000 concurrent socket fds, so the default 1024 limit causes connection resets. It's also a _per-process_ limit, so with 8 workers the load spreads and each worker only hits it at very high per-worker concurrency.

## Benchmark details

```
docker compose up -d

# Benchmark FastAPI directly

➜ curl http://localhost:8000/
Hello World

➜ ab -n 80000 -c 100 http://localhost:8000/

This is ApacheBench, Version 2.3 <$Revision: 1934973 $>
Copyright 1996 Adam Twiss, Zeus Technology Ltd, http://www.zeustech.net/
Licensed to The Apache Software Foundation, http://www.apache.org/

Benchmarking localhost (be patient)
Completed 8000 requests
Completed 16000 requests
Completed 24000 requests
Completed 32000 requests
Completed 40000 requests
Completed 48000 requests
Completed 56000 requests
Completed 64000 requests
Completed 72000 requests
Completed 80000 requests
Finished 80000 requests


Server Software:
Server Hostname:        localhost
Server Port:            8000

Document Path:          /
Document Length:        11 bytes

Concurrency Level:      100
Time taken for tests:   2.305 seconds
Complete requests:      80000
Failed requests:        0
Total transferred:      11760000 bytes
HTML transferred:       880000 bytes
Requests per second:    34705.95 [#/sec] (mean)
Time per request:       2.881 [ms] (mean)
Time per request:       0.029 [ms] (mean, across all concurrent requests)
Transfer rate:          4982.20 [Kbytes/sec] received

Connection Times (ms)
              min  mean[+/-sd] median   max
Connect:        0    0   0.1      0       1
Processing:     0    3   0.3      3       8
Waiting:        0    3   0.3      3       8
Total:          0    3   0.3      3       8

Percentage of the requests served within a certain time (ms)
  50%      3
  66%      3
  75%      3
  80%      3
  90%      3
  95%      3
  98%      4
  99%      4
 100%      8 (longest request)


# Benchmark FastAPI via Traefik

➜ curl -H "Host: api.localhost" http://localhost:80/

Hello World

➜ ab -n 80000 -c 100 -H "Host: api.localhost" http://localhost:80/

This is ApacheBench, Version 2.3 <$Revision: 1934973 $>
Copyright 1996 Adam Twiss, Zeus Technology Ltd, http://www.zeustech.net/
Licensed to The Apache Software Foundation, http://www.apache.org/

Benchmarking localhost (be patient)
Completed 8000 requests
Completed 16000 requests
Completed 24000 requests
Completed 32000 requests
Completed 40000 requests
Completed 48000 requests
Completed 56000 requests
Completed 64000 requests
Completed 72000 requests
Completed 80000 requests
Finished 80000 requests


Server Software:
Server Hostname:        localhost
Server Port:            80

Document Path:          /
Document Length:        11 bytes

Concurrency Level:      100
Time taken for tests:   2.308 seconds
Complete requests:      80000
Failed requests:        0
Total transferred:      10240000 bytes
HTML transferred:       880000 bytes
Requests per second:    34661.79 [#/sec] (mean)
Time per request:       2.885 [ms] (mean)
Time per request:       0.029 [ms] (mean, across all concurrent requests)
Transfer rate:          4332.72 [Kbytes/sec] received

Connection Times (ms)
              min  mean[+/-sd] median   max
Connect:        0    0   0.2      0       1
Processing:     0    3   1.7      2      47
Waiting:        0    2   1.7      2      47
Total:          1    3   1.7      3      48

Percentage of the requests served within a certain time (ms)
  50%      3
  66%      3
  75%      3
  80%      4
  90%      4
  95%      5
  98%      5
  99%      6
 100%     48 (longest request)

```

API Gateway benchmark: https://github.com/howardjohn/gateway-api-bench
