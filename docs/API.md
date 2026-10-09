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
- `ceiling_height`: The ceiling height on this floor in feet (default: `9`,
  must be over 0 and at most 40). Every room gets it unless the plan prints its
  own height for that room (a vaulted great room keeps its 18'). It sets the
  spacing of the recessed grid: half the ceiling height between cans.

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
      "labeled": true,
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
  "page": 1,
  "measured_sqft": 1480.0,
  "ceiling_height_ft": 9.0
}
```

- `labeled` is `false` for a space with no name printed in it (an unlabeled
  bath or closet). Its `name` and `room_type` are the model's guess, and it
  still gets fixtures; a client should ask the user to confirm the name, via
  the room update endpoint below. Only the upload response carries it.
- `measured_sqft` is the conditioned area of the rooms on this page, measured
  at the plan's scale. The scale is read from rooms whose sizes are printed on
  the plan; `null` when there are none, and room sizes are then estimates.
- Room boxes (`bbox_*`) sit on the inside faces of the walls drawn around each
  room where walls could be found, and recessed cans are laid out on a grid
  inside them.

This endpoint is synchronous. It saves the file, calls Vision to parse rooms, runs the lighting engine to assign fixtures and stores everything in the database. Expect 5 to 15 seconds for the AI analysis.

**Multi-page PDFs:** one page is analyzed per request — the one named by
`page`. Every `plan_x`/`plan_y` is a fraction of that page, so it must be the
page the client is drawing; reading a whole plan set at once would return
coordinates measured against sheets the viewer is not showing. `page_count` is
the pages in the uploaded file, so a client can offer the others; the viewer
shows one page per floor and sends every page for analysis as soon as the user
has given the ceiling heights, two at a time. The model calls run off the
server's event loop, so pages analyze in parallel.
`POST /api/projects/{id}/plans/{plan_id}/parse` takes the same `page`.

Fixture placement runs a second Vision pass. That pass is best-effort: if it
fails, the response still comes back `201` with fixtures positioned by the
algorithmic layout rather than failing the upload.

### Re-parse Plan

```
POST /api/projects/{project_id}/plans/{plan_id}/parse
```

Deletes existing rooms and fixtures, re-runs the Vision parser and lighting engine. Takes the same `page` and `ceiling_height` as upload, and returns the same response body.

### Update a Room

```
PATCH /api/projects/{project_id}/plans/{plan_id}/rooms/{room_id}
Content-Type: application/json

{"name": "Hall Bath", "room_type": "bathroom", "ceiling_height_ft": 9}
```

All fields are optional. This is how a user names a space the plan left
unlabeled. Renaming keeps the room's fixtures. Changing `room_type` or
`ceiling_height_ft` lays the room's fixtures out again for what it really is,
on the grid inside its walls.

**Response:** `200 OK` with the room, as in the upload response. `400` for an
empty name or an unknown `room_type`, `404` if the room is not on that plan of
that project, `409` if another room on the plan already has the name.

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
