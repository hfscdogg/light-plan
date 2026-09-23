# LightPlan API Reference

Base URL: `http://localhost:8000/api`

## Projects

### Create Project

```
POST /api/projects
```

**Request Body:**
```json
{
  "name": "Smith Residence",
  "address": "123 Oak Lane, Lot 4",
  "tier": "better",
  "builder_id": null
}
```

**Response:** `201 Created`
```json
{
  "id": "uuid",
  "name": "Smith Residence",
  "address": "123 Oak Lane, Lot 4",
  "status": "draft",
  "tier": "better",
  "created_at": "2025-01-15T10:00:00Z",
  "updated_at": "2025-01-15T10:00:00Z",
  "floor_plans": [],
  "builder": null
}
```

### List Projects

```
GET /api/projects?status=assigned&limit=20&offset=0
```

**Response:** `200 OK`
```json
[
  {
    "id": "uuid",
    "name": "Smith Residence",
    "address": "123 Oak Lane, Lot 4",
    "status": "assigned",
    "tier": "better",
    "created_at": "2025-01-15T10:00:00Z",
    "updated_at": "2025-01-15T10:30:00Z"
  }
]
```

### Get Project Detail

```
GET /api/projects/{project_id}
```

**Response:** `200 OK`

Returns the full project with nested floor plans, rooms and fixtures.

### Update Project

```
PATCH /api/projects/{project_id}
```

**Request Body:** (partial update)
```json
{
  "tier": "best"
}
```

### Delete Project

```
DELETE /api/projects/{project_id}
```

**Response:** `204 No Content`

Cascades to delete all floor plans, rooms and fixtures.

## Floor Plans

### Upload and Parse

```
POST /api/projects/{project_id}/plans/upload
Content-Type: multipart/form-data
```

**Form Fields:**
- `file`: The floor plan file (PDF, PNG or JPG)

**Query Parameters:**
- `page`: Which page of a PDF to analyze, 1-based (default: `1`). A page past
  the end of the file, or any page other than 1 for an image, is a `400`.

**Response:** `201 Created`
```json
{
  "floor_plan_id": "uuid",
  "status": "assigned",
  "rooms": [
    {
      "id": "uuid",
      "name": "Kitchen",
      "room_type": "kitchen",
      "sqft": 180.0,
      "width_ft": 15.0,
      "length_ft": 12.0,
      "ceiling_height_ft": 9.0,
      "fixtures": [
        {
          "id": "uuid",
          "fixture_type": "recessed",
          "product_sku": "DMF-DID210",
          "product_desc": "DMF DID Series 2\" recessed",
          "msrp_range": "$80-120",
          "zone": "kitchen-general",
          "position_x": 0.15,
          "position_y": 0.15,
          "notes": "",
          "is_prewire": false
        }
      ]
    }
  ],
  "page_count": 3,
  "pages_analyzed": 1,
  "page": 1
}
```

This endpoint is synchronous. It saves the file, calls Vision to parse rooms, runs the lighting engine to assign fixtures and stores everything in the database. Expect 5 to 15 seconds for the AI analysis.

**Multi-page PDFs:** one page is analyzed per request — the one named by
`page`. Every `plan_x`/`plan_y` is a fraction of that page, so it must be the
page the client is drawing; reading a whole plan set at once would return
coordinates measured against sheets the viewer is not showing. `page_count` is
the pages in the uploaded file, so a client can offer the others; the viewer
shows one page per floor and analyzes each the first time it is opened.
`POST /api/projects/{id}/plans/{plan_id}/parse` takes the same `page`.

Fixture placement runs a second Vision pass. That pass is best-effort: if it
fails, the response still comes back `201` with fixtures positioned by the
algorithmic layout rather than failing the upload.

### Re-parse Plan

```
POST /api/projects/{project_id}/plans/{plan_id}/parse
```

Deletes existing rooms and fixtures, re-runs the Vision parser and lighting engine. Same response body as upload.

### Get Plan Detail

```
GET /api/projects/{project_id}/plans/{plan_id}
```

Returns the floor plan with nested rooms and fixtures.

## Exports

### Download PDF

```
GET /api/exports/projects/{project_id}/pdf
```

**Response:** `200 OK` with `Content-Type: application/pdf`

Returns a branded PDF containing:
- Cover page with project info and "Why Smart Lighting" introduction
- Fixture schedule grouped by room
- Product recommendations and MSRP ranges for the selected tier

Query parameters:
- `include_cover`: Include cover page (default: `true`)
