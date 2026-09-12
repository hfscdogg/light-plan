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
  "pages_analyzed": 1
}
```

This endpoint is synchronous. It saves the file, calls Vision to parse rooms, runs the lighting engine to assign fixtures and stores everything in the database. Expect 5 to 15 seconds for the AI analysis.

**Multi-page PDFs:** only the first page is analyzed. Every `plan_x`/`plan_y`
is a fraction of the analyzed page, and clients render page 1, so reading a
whole plan set would return coordinates measured against a sheet the viewer
never draws. `page_count` is the pages in the uploaded file and
`pages_analyzed` how many were read — show the difference to the user and
have them upload further sheets as separate plans.

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
