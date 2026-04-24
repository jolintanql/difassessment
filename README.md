# Social Media Crawler — Instagram Downloader

A containerized backend service built with Azure Durable Functions for downloading public Instagram posts and reels using the SociaVault API.

The service accepts a profile identifier, starts crawling asynchronously, stores normalized results in SQLite, and exposes endpoints for artifact creation, retrieval, health monitoring, and blob serving for downloaded media.

---

## Features

- Asynchronous crawl execution using Azure Durable Functions
- Support for public Instagram posts and reels
- SQLite-based persistence for artifacts, contents, and blob metadata
- Pagination support for posts and reels
- Duplicate in-progress request detection
- Local blob serving for downloaded media
- Anonymous local routes for simpler evaluation and local testing

---

## Implemented Endpoints

- `POST /api/artifacts`
  - Starts a new crawl using `case_id`, `identifier`, and `description`
  - Supports pagination requests using `case_id`, `artifact_id`, and `content_type`
  - Returns an `artifact_id` immediately
  - Reuses the same `artifact_id` if the same request is already in progress
- `GET /api/artifacts`
  - Returns all stored artifacts
- `GET /api/artifacts/{id}`
  - Returns a specific artifact with metadata and contents
- `GET /api/health`
  - Returns `{"status": "ok"}`
- `GET /api/blob/{blob_id}`
  - Serves downloaded media files from local storage

---

## Local Setup

### Requirements

- [Python 3.10 - 3.13](https://www.python.org/downloads/)
- [Docker / Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [Azure Functions Core Tools](https://learn.microsoft.com/en-us/azure/azure-functions/functions-run-local)
- [SociaVault API Key](https://sociavault.com/)

### Option 1: Run with Docker Compose

This option starts both the application and Azurite in containers. The application is exposed on port `8080`.

Create a `.env` file:

```env
SOCIAVAULT_API_KEY=your_real_api_key_here
```

Start the application:

```shell
docker compose up --build
```

Verify that both services are running:

```shell
docker compose ps
```

![Docker Compose Service Status](./screenshots/docker-compose-ps.png)

On Apple Silicon, the Compose file uses `platform: linux/amd64` for compatibility.

### Option 2: Run with Azure Functions Core Tools

The API screenshots and example responses below were captured using this local development mode on port `7071`.

Azure Durable Functions requires Azure Storage for orchestration state. For local development, Azurite is used as the storage emulator.

Create and activate a virtual environment:

```shell
python -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```shell
pip install -r requirements.txt
```

Create `local.settings.json`:

```json
{
  "IsEncrypted": false,
  "Values": {
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "AzureWebJobsFeatureFlags": "EnableWorkerIndexing",
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "SOCIAVAULT_API_KEY": "<your_api_key>"
  }
}
```

Start Azurite:

```shell
docker run -d -p 10000:10000 -p 10001:10001 -p 10002:10002 mcr.microsoft.com/azure-storage/azurite
```

Start the Functions app:

```shell
func start
```

---

## API Examples

### Health Check

```shell
curl -s http://localhost:7071/api/health | jq
```

**Response**

```json
{
  "status": "ok"
}
```

![Health Check Screenshot](./screenshots/health-check.png)

### Start New Download

```shell
curl -s -X POST http://localhost:7071/api/artifacts \
  -H "Content-Type: application/json" \
  -d '{"case_id":"123","identifier":"mothershipsg","description":"Instagram Profile of Mothership"}' | jq
```

**Response**

```json
{
  "artifact_id": "XXX"
}
```

![Start Download Screenshot](./screenshots/start-download.png)

### Poll Artifact Status

```shell
curl -s http://localhost:7071/api/artifacts/<artifact_id> | jq
```

**Response**

```json
{
  "status": "processing",
  "has_more_data": [
    { "content_type": "post", "has_more_data": false },
    { "content_type": "reel", "has_more_data": false }
  ],
  "metadata": {
    "platform": "instagram",
    "identifier": "mothershipsg",
    "description": "Instagram Profile of Mothership"
  }
}
```

![Artifact Processing Screenshot](./screenshots/artifact-processing.png)

### Completed Artifact Response

```shell
curl -s http://localhost:7071/api/artifacts/<artifact_id> | jq '{status, metadata: {identifier: .metadata.identifier}, contents: [.contents[0] | {content_type, media_content: [.media_content[0] | {url}]}]}'
```

**Response**

```json
{
  "status": "success",
  "metadata": {
    "identifier": "mothershipsg"
  },
  "contents": [
    {
      "content_type": "post",
      "media_content": [
        {
          "url": "/api/blob/<blob_id>"
        }
      ]
    }
  ]
}
```

![Artifact Success Screenshot](./screenshots/artifact-success.png)

### Pagination

Pagination is triggered with a `POST /api/artifacts` request using the existing `artifact_id` and a `content_type` such as `post` or `reel`.

```shell
curl -s -X POST http://localhost:7071/api/artifacts \
  -H "Content-Type: application/json" \
  -d '{"case_id":"123","artifact_id":"<artifact_id>","content_type":"post"}' | jq
```

**Response**

```json
{
  "artifact_id": "XXX"
}
```

To verify that pagination appended more results, the artifact can be queried again and the content count compared:

```shell
curl -s http://localhost:7071/api/artifacts/<artifact_id> | jq '{status, content_count: (.contents | length)}'
```

**Example Result**

```json
{
  "status": "success",
  "content_count": 36
}
```

![Pagination Screenshot](./screenshots/pagination.png)

### Blob Response

Blob URLs returned in artifact contents can be downloaded directly through the blob endpoint.

```shell
curl -s http://localhost:7071/api/blob/<blob_id> --output test.jpg
```

**Response**

The requested file is returned with the correct `Content-Type`, such as `image/jpeg` or `video/mp4`.

![Blob Serving Screenshot](./screenshots/blob-serving.png)

---

## Data Storage

SQLite is used as the persistence layer with three tables:

- `artifacts` — artifact metadata, status, and pagination cursors
- `contents` — normalized post and reel data
- `blobs` — downloaded file paths and blob identifiers

---

## Design Considerations

### Normalization layer for inconsistent upstream responses

SociaVault responses differ between image posts, video posts, carousel posts, and reels. The normalization layer converts these different response shapes into a single consistent output format so the stored data and API responses remain predictable across content types.

### Pagination support

Pagination state is stored so that additional pages of posts or reels can be retrieved without restarting the crawl from the beginning. This makes the API more practical for profiles with larger amounts of content and allows artifact retrieval to continue incrementally.

### Extensibility

The external API integration is separated from the orchestration and persistence layers, making it easier to extend the service to other platforms in the future without changing the overall workflow. This keeps the implementation modular and easier to maintain.

---

## Testing

Run the test suite with:

```shell
pytest tests/ -v
```

### Testing approach and justification

The test coverage focuses on the parts of the system that contain the most important application logic and can be validated reliably without depending on a live SociaVault request or full Azure infrastructure.

#### `tests/test_external_api.py`

These tests verify the normalization layer because the upstream API can return different structures for image posts, video posts, carousel posts, and reels. The tests confirm that media URLs are extracted correctly, invalid reels are filtered out, and pagination fields are parsed as expected.

#### `tests/test_db.py`

These tests verify duplicate-request handling and persistence-related behavior. The tests confirm that an existing in-progress artifact is reused and that a new crawl can start when no matching in-progress artifact exists.

This testing strategy prioritizes correctness for the core transformation and persistence logic while keeping the test suite lightweight and fast to run locally.

![Test Results Screenshot](./screenshots/tests-passing.png)

---


```
