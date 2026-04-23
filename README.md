# Social Media Crawler — Instagram Downloader

A social media crawler backend built with Azure Durable Functions that downloads Instagram posts and reels from public profiles using the SociaVault API.

## Available Endpoints

- `POST /api/artifacts`
  - Accepts a JSON containing `case_id`, `identifier` and `description` to trigger a new download
  - Accepts a JSON containing `case_id`, `artifact_id` and `content_type` to paginate for the next page of results (optional)
  - Returns an `artifact_id` immediately — non-blocking
  - If a download is still processing for the same `case_id` and `identifier`, returns the existing `artifact_id`
  - Triggers `polling_orchestrator` in `api_blueprint.py`
- `GET /api/artifacts`
  - Lists all artifacts (processing or completed)
- `GET /api/artifacts/{id}`
  - Gets a specific artifact by ID with full contents
- `GET /api/health`
  - Returns `{"status": "ok"}` if healthy
- `GET /api/blob/{blob_id}` (Optional)
  - Serves downloaded media files directly for viewing in the browser

## Local Setup

### Requirements
- [Python 3.10 - 3.13](https://www.python.org/downloads/)
- [Docker / Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [Azure Function Core Tools](https://learn.microsoft.com/en-us/azure/azure-functions/functions-run-local)
- [SociaVault API Key](https://sociavault.com/)

This project uses Azure Durable Functions internally. For Azure Functions to work, you need Python runtime between 3.10 to 3.13.

Ensure you have python (3.10 - 3.13) installed. Run the following commands to build a virtual environment:
```shell
python -m venv .venv
```
For Windows:
```shell
.venv\Scripts\activate
```
For MacOS/Linux:
```shell
source .venv/bin/activate
```
Install the required packages:
```shell
pip install -r requirements.txt
```

A `local.settings.json` file stores app settings and settings used by local development tools for Azure Functions. You may read more about them [here](https://learn.microsoft.com/en-us/azure/azure-functions/functions-develop-local). Create the file with the following contents:
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

For Durable Functions to work, it requires connection to blob storage. For local testing, we can run a fake Azure Blob using Azurite. We can run Azurite using docker, by running the following command:

```docker
docker run -d -p 10000:10000 -p 10001:10001 -p 10002:10002 mcr.microsoft.com/azure-storage/azurite
```

Now you should be able to start the durable function by running the following command:
```shell
func start
```

## Architecture

The backend uses **Azure Durable Functions** to handle long-running downloads without blocking the HTTP response.

```
POST /api/artifacts
        |
        v
trigger_download (HTTP Trigger)
        |
        v
polling_orchestrator (Orchestrator)
        |
        |-- startJob (Activity)
        |       |-- Calls SociaVault API (profile, posts, reels)
        |       |-- Downloads media files to local blob storage
        |       `-- Saves results to SQLite
        |
        `-- updateStatus (Activity)
                `-- Updates artifact status to success/failed
```

1. `POST /api/artifacts` triggers `polling_orchestrator` and returns `artifact_id` immediately
2. `polling_orchestrator` calls `startJob` which hits SociaVault API
3. Media files are downloaded and stored locally
4. Results are saved to SQLite and status updated to `success` or `failed`
5. Client polls `GET /api/artifacts/{id}` until status is `success`

## Design Considerations

### Future Social Media Integration

The solution is designed with future extensibility in mind. The normalization functions in `external_api.py` produce a platform-agnostic output format (posts, reels, metadata) that other social media platforms can map to. The orchestrator, database, and HTTP endpoints remain unchanged when adding a new platform — only `external_api.py` requires new normalization functions and a new base URL for the target platform. For example, adding TikTok support via SociaVault would only require a new `TIKTOK_BASE_URL` and corresponding `_normalize_tiktok_post` and `_normalize_tiktok_posts_response` functions.

### Media Normalization

SociaVault returns videos in multiple qualities inside a `video_versions` array. The `_extract_best_video` function picks the highest quality version. It also handles fallbacks — if `video_versions` doesn't exist, it tries `video_url` directly, then checks inside a nested `media` object. This ensures robust extraction across different API response shapes.

### Error Handling

- Failed API calls are caught and logged — the artifact status is set to `"failed"`
- Reel fetch timeouts do not kill the whole job — posts are still saved
- Failed blob downloads are logged and skipped — the job continues without that media file
- Duplicate prevention — if the same `case_id` and `identifier` is still processing, the existing `artifact_id` is returned

### Pydantic Models

Response serialization uses Pydantic models (`models/artifact.py`) to validate and serialize API responses. `exclude_none=True` automatically drops optional fields like `url`, `thumbnail_url`, `display_name`, and `profile_pic` when they are not available, keeping responses clean and spec-compliant.

### Database

SQLite with three tables:

- **artifacts** — stores metadata, status, and pagination cursors
- **contents** — stores normalized post and reel data
- **blobs** — stores downloaded media file paths and blob IDs

## API Documentation

### POST /api/artifacts — New Download

**Request:**
```json
{
  "case_id": "123",
  "identifier": "mothershipsg",
  "description": "Instagram Profile of Mothership"
}
```

**Response:**
```json
{
  "artifact_id": "XXX"
}
```

### POST /api/artifacts — Pagination (Optional)

**Request:**
```json
{
  "case_id": "123",
  "artifact_id": "XXX",
  "content_type": "post"
}
```

**Response:**
```json
{
  "artifact_id": "XXX"
}
```

### GET /api/artifacts and GET /api/artifacts/{id}

**Response:**
```json
[
  {
    "status": "success",
    "has_more_data": [
      {"content_type": "post", "has_more_data": true},
      {"content_type": "reel", "has_more_data": true}
    ],
    "metadata": {
      "platform": "instagram",
      "identifier": "mothershipsg",
      "display_name": "Mothership",
      "profile_pic": "http://<image_url>",
      "description": "Instagram Profile of Mothership"
    },
    "contents": [
      {
        "error_message": "",
        "owners": ["mothershipsg"],
        "caption": "XXX",
        "datetime": "2024-01-01T12:12:12Z",
        "content_type": "post",
        "media_content": [
          {
            "media_type": "image",
            "original_url": "http://<image_url>",
            "url": "/api/blob/<blob_id>"
          },
          {
            "media_type": "video",
            "original_url": "http://<image_url>",
            "original_thumbnail_url": "http://<image_url>",
            "url": "/api/blob/<blob_id>",
            "thumbnail_url": "/api/blob/<blob_id>"
          }
        ]
      },
      {
        "error_message": "",
        "owners": ["mothershipsg"],
        "caption": "XXX",
        "datetime": "2024-02-01T12:12:12Z",
        "content_type": "reel",
        "media_content": [
          {
            "media_type": "video",
            "original_url": "http://<image_url>",
            "original_thumbnail_url": "http://<image_url>",
            "url": "/api/blob/<blob_id>",
            "thumbnail_url": "/api/blob/<blob_id>"
          }
        ]
      }
    ]
  },
  {
    "status": "processing",
    "has_more_data": [
      {"content_type": "post", "has_more_data": false},
      {"content_type": "reel", "has_more_data": false}
    ],
    "metadata": {
      "platform": "instagram",
      "identifier": "mothershipsg",
      "description": "Instagram Profile of Mothership"
    },
    "contents": []
  }
]
```

### GET /api/health

**Response:**
```json
{"status": "ok"}
```

### GET /api/blob/{blob_id}

Returns raw file content with appropriate `Content-Type` header (e.g. `image/jpeg`, `video/mp4`).

## Example Requests & Responses

### Health Check
```shell
curl -s http://localhost:7071/api/health | jq
```

### Trigger New Download
```shell
curl -s -X POST http://localhost:7071/api/artifacts \
  -H "Content-Type: application/json" \
  -d '{"case_id": "123", "identifier": "mothershipsg", "description": "Instagram Profile of Mothership"}' | jq
```

### Poll for Status
```shell
curl -s http://localhost:7071/api/artifacts/<artifact_id> | jq '{status, has_more_data, metadata}'
```

### List All Artifacts
```shell
curl -s http://localhost:7071/api/artifacts | jq
```

### Paginate Posts
```shell
curl -s -X POST http://localhost:7071/api/artifacts \
  -H "Content-Type: application/json" \
  -d '{"case_id": "123", "artifact_id": "<artifact_id>", "content_type": "post"}' | jq
```

### Serve Blob
```shell
curl -s http://localhost:7071/api/blob/<blob_id> --output test.jpg && open test.jpg
```

## Running Tests

```shell
pip install pytest
pytest tests/ -v
```

### Why these tests

The unit tests focus on two areas: the normalization functions in `external_api.py` and the idempotency logic in `db.py`. These were chosen because they contain the most critical business logic that is also easily testable without requiring a live API connection or database.

**`tests/test_external_api.py`** — The SociaVault API returns raw Instagram data in varying shapes depending on the content type (image, video, carousel, reel). The normalization functions parse and transform this raw data into the standardized format expected by the app. Testing these in isolation ensures:

- Image posts are correctly identified and their URLs extracted
- Video posts pick the highest quality URL from the `video_versions` array
- Carousel posts return all media items, not just the first one
- Reels with no video URL are filtered out and not saved to the database
- Pagination cursors and `more_available` flags are correctly extracted from both posts and reels responses
- The `content_type` field is always set correctly (`"post"` or `"reel"`)
- The `owners` field always contains the identifier of the profile being crawled

**`tests/test_db.py`** — If a download is still processing, the same `artifact_id` should be returned instead of starting a new job. Testing this ensures:

- `find_in_progress_artifact` correctly returns an existing `artifact_id` when a matching processing record exists
- `find_in_progress_artifact` returns `None` when no matching record is found, allowing a new download to be triggered
```

