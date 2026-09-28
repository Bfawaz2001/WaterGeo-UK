# Phase 13 explorer design

Phase 13 turns the existing explorer workflows into a coherent public-facing product
without changing API, source, search or snapshot semantics. WaterGeo remains an
independent local or self-hosted project; this work does not claim public hosting.

## Visual system

The explorer defines its typography, spacing, surfaces, borders, elevation, focus,
source and status colours as CSS custom properties. Local SVG symbols identify each
source in layer controls, search results and selected-feature headers, so colour is
not the only distinction. MapLibre stays demand-loaded and the phase adds no runtime
dependency or chart framework.

The application shell gives the map the largest practical area. Search is the main
discovery control, layers use compact toggle cards, source health collapses to a
summary when healthy, and selected-feature details float above the map on desktop or
use a bottom sheet on small screens.

## Information hierarchy

Selected features show a name, source identity and primary facts first. Source-specific
cards then present observations, publisher metadata, a reservoir trend or an event
timeline. Provenance remains directly visible and exact snapshot, licence and geometry
presentation fields remain available in labelled disclosures.

The reservoir chart uses exact publisher values. It highlights the last value, states
the edition range, exposes every point to pointer and keyboard focus, and displays the
focused date and value. It does not interpolate values or infer restrictions, safety
or supply risk.

Hydrology observations retain every publisher measure. The publisher measure ID is
shown beside the human-readable parameter so equal-looking observations are still
distinguishable. Thames status, observation time and WaterGeo retrieval time remain
separate. Water-supply transformation details are retained behind a technical
disclosure beneath the dated-boundary warning.

## Bounded discovery

Map counts remain counts of bounded loaded results. The Water Body browser explicitly
states how many loaded records match and that its local filter is not a national
search. Loading another page stays snapshot pinned. Universal search keeps the bounded
server contract and adds grouped source symbols plus Arrow Up, Arrow Down, Enter and
Escape keyboard behaviour.

A dismissible first-visit card explains search, layers, selection and provenance. Its
dismissal is stored only in the browser. It does not block map use or require an
account.

## Acceptance criteria

Visual acceptance covers clustered Hydrology, each selected-feature family, the
reservoir chart, Water Body browsing, expanded source health, grouped search and a
390-pixel mobile viewport against the complete local demo. Review confirms:

- the map remains the dominant surface;
- the first action is apparent from search and the short introduction;
- the control area gives primary actions priority over operational detail;
- every feature uses summary, supporting detail and provenance in that order;
- caveats remain visible beside claims they qualify;
- static editions and latest accepted retrievals use explicit wording;
- mobile controls collapse and details use a scrollable bottom sheet.

Pixel snapshots are intentionally limited because the MapLibre canvas and local demo
data change independently of the product shell. Browser tests assert stable structure,
semantics and representative source states; manual acceptance inspects the rendered
production build.
