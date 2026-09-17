-- Invented planar shapes under the repository MIT licence, not publisher data.
-- Read-only experiment: no application tables, writes, repair approval, or CRS conversion.
WITH cases(case_id, wkt) AS (
    VALUES
        ('valid_hole', 'POLYGON((0 0,10 0,10 10,0 10,0 0),(2 2,2 4,4 4,4 2,2 2))'),
        ('bow_tie', 'POLYGON((0 0,10 10,0 10,10 0,0 0))'),
        ('nested_holes',
         'POLYGON((0 0,10 0,10 10,0 10,0 0),(2 2,2 8,8 8,8 2,2 2),(3 3,3 4,4 4,4 3,3 3))'),
        ('overlapping_parts',
         'MULTIPOLYGON(((0 0,4 0,4 4,0 4,0 0)),((2 2,6 2,6 6,2 6,2 2)))'),
        ('collapsed_polygon', 'POLYGON((0 0,5 0,10 0,0 0))'),
        ('spike', 'POLYGON((0 0,10 0,10 10,5 10,5 15,5 10,0 10,0 0))')
), methods(method, parameters) AS (
    VALUES
        ('linework', 'method=linework'),
        ('structure_keep', 'method=structure keepcollapsed=true'),
        ('structure_drop', 'method=structure keepcollapsed=false')
), inputs AS (
    SELECT case_id, wkt, public.ST_GeomFromText(wkt, 27700) AS original
    FROM cases
), candidates AS MATERIALIZED (
    SELECT case_id, wkt, original, method, parameters,
           public.ST_MakeValid(original, parameters) AS candidate,
           public.ST_IsValidDetail(original, 0) AS original_validity
    FROM inputs CROSS JOIN methods
)
SELECT case_id, method, parameters, wkt AS original_wkt,
       encode(public.ST_AsEWKB(original, 'NDR'), 'hex') AS original_ewkb_hex,
       (original_validity).valid AS original_valid,
       (original_validity).reason AS original_invalid_reason,
       public.ST_AsText((original_validity).location) AS original_invalid_location,
       public.ST_Area(original) AS original_area_untrusted_m2,
       public.ST_AsText(candidate) AS candidate_wkt,
       encode(public.ST_AsEWKB(candidate, 'NDR'), 'hex') AS candidate_ewkb_hex,
       public.GeometryType(candidate) AS candidate_type,
       public.ST_IsValid(candidate, 0) AS candidate_valid,
       public.ST_IsEmpty(candidate) AS candidate_empty,
       public.ST_SRID(candidate) AS candidate_srid,
       public.ST_NDims(candidate) AS candidate_dimensions,
       public.ST_Area(candidate) AS candidate_area_m2,
       public.ST_NumGeometries(candidate) AS candidate_parts,
       EXISTS (
           SELECT 1 FROM public.ST_Dump(candidate) AS part
           WHERE public.ST_Dimension(part.geom) < 2
       ) AS has_lower_dimension_parts,
       public.ST_Equals(candidate, public.ST_MakeValid(candidate, parameters))
           AS repair_is_topologically_idempotent,
       public.ST_AsEWKB(original, 'NDR') = public.ST_AsEWKB(candidate, 'NDR')
           AS coordinates_unchanged,
       public.ST_Covers(candidate, public.ST_SetSRID(public.ST_Point(3.5, 3.5), 27700))
           AS covers_probe_3_5,
       public.ST_Covers(candidate, public.ST_SetSRID(public.ST_Point(3, 3), 27700))
           AS covers_probe_3_3,
       public.GeometryType(candidate) IN ('POLYGON', 'MULTIPOLYGON')
           AND NOT public.ST_IsEmpty(candidate)
           AND public.ST_IsValid(candidate, 0)
           AND public.ST_SRID(candidate) = 27700
           AND public.ST_NDims(candidate) = 2 AS meets_geometry_checks_after_multi
FROM candidates
ORDER BY case_id, method;
