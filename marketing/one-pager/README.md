# LightPlan one-pager

A one-page flyer that shows a builder **their own plan**, lit two ways: the way
it gets wired today (one spray-painted circle per room at rough-in) and the
LightPlan version with every fixture placed. It goes out finished; the email
does not ask the builder to send anything.

## Making one for a builder

1. Pick one plan from the builder's website or brochure and save the floorplan
   image (`prospects/<builder>-bare.jpg`).
2. Upload it to LightPlan, slide to Level 4, and screenshot the lit plan at the
   same crop (`prospects/<builder>-lit.jpg`). Note the fixture count and the
   price range for each level.
3. Copy `prospects/sample.json` to `prospects/<builder>.json` and fill in the
   builder, plan name, both images, fixture count, level prices, and `rooms`:
   one `[x%, y%]` point per room on the bare plan, where its builder-standard
   box would go. These are the room centers LightPlan reads off the plan.
4. Run `node marketing/one-pager/build.js marketing/one-pager/prospects/<builder>.json`.
   The PDF and a PNG preview land in `out/`. The script warns if a long plan
   name pushes the page past one sheet.

`LightPlan-sample.pdf` is the generic version built from `prospects/sample.json`.
