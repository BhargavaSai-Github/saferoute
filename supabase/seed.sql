-- ==============================================================================
-- SafeRoute - Seed Data (Kukatpally Y Junction, Hyderabad)
-- Reference: docs/SPEC.md Section 7, 10, 14
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- 1. Demo User Profiles (Admin & Citizen)
-- ------------------------------------------------------------------------------
-- Note: In local/hosted Supabase, users are created in auth.users.
-- We insert demo users into auth.users (if not present) and public.profiles.
DO $$
DECLARE
    v_admin_id UUID := '00000000-0000-0000-0000-000000000001';
    v_user1_id UUID := '00000000-0000-0000-0000-000000000002';
    v_user2_id UUID := '00000000-0000-0000-0000-000000000003';
    v_user3_id UUID := '00000000-0000-0000-0000-000000000004';
BEGIN
    -- Insert auth.users stub records if running in Supabase environment
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'auth' AND table_name = 'users') THEN
        INSERT INTO auth.users (id, instance_id, email, encrypted_password, email_confirmed_at, raw_app_meta_data, raw_user_meta_data, created_at, updated_at, role, aud)
        VALUES 
            (v_admin_id, '00000000-0000-0000-0000-000000000000', 'admin@saferoute.demo', crypt('AdminPass@123', gen_salt('bf')), NOW(), '{"provider":"email","providers":["email"]}', '{"full_name":"Civic Administrator"}', NOW(), NOW(), 'authenticated', 'authenticated'),
            (v_user1_id, '00000000-0000-0000-0000-000000000000', 'priya.sharma@saferoute.demo', crypt('CitizenPass@123', gen_salt('bf')), NOW(), '{"provider":"email","providers":["email"]}', '{"full_name":"Priya Sharma"}', NOW(), NOW(), 'authenticated', 'authenticated'),
            (v_user2_id, '00000000-0000-0000-0000-000000000000', 'rahul.reddy@saferoute.demo', crypt('CitizenPass@123', gen_salt('bf')), NOW(), '{"provider":"email","providers":["email"]}', '{"full_name":"Rahul Reddy"}', NOW(), NOW(), 'authenticated', 'authenticated'),
            (v_user3_id, '00000000-0000-0000-0000-000000000000', 'ananya.rao@saferoute.demo', crypt('CitizenPass@123', gen_salt('bf')), NOW(), '{"provider":"email","providers":["email"]}', '{"full_name":"Ananya Rao"}', NOW(), NOW(), 'authenticated', 'authenticated')
        ON CONFLICT (id) DO NOTHING;
    END IF;

    -- Upsert public.profiles
    INSERT INTO public.profiles (id, full_name, role, created_at)
    VALUES
        (v_admin_id, 'Civic Administrator (GHMC)', 'admin', NOW() - INTERVAL '60 days'),
        (v_user1_id, 'Priya Sharma', 'user', NOW() - INTERVAL '50 days'),
        (v_user2_id, 'Rahul Reddy', 'user', NOW() - INTERVAL '40 days'),
        (v_user3_id, 'Ananya Rao', 'user', NOW() - INTERVAL '30 days')
    ON CONFLICT (id) DO UPDATE SET role = EXCLUDED.role, full_name = EXCLUDED.full_name;
END $$;

-- ------------------------------------------------------------------------------
-- 2. Seed Hazard Reports around Kukatpally Y Junction (17.4849° N, 78.4138° E)
-- ------------------------------------------------------------------------------
INSERT INTO public.hazard_reports (
    id, reporter_id, category, description, location, address_text, status,
    escalation_recommended, severity_score, confidence, confirm_count, dispute_count,
    fixed_count, ai_suggested_category, ai_confidence, is_seed, created_at, updated_at
) VALUES
-- 1. High-severity pothole at Kukatpally Y Junction flyover ramp
(
    '11111111-0000-0000-0000-000000000001',
    '00000000-0000-0000-0000-000000000002',
    'pothole',
    'Deep crater on left lane right before the flyover ascent. Causing sudden swerving and vehicle damage.',
    ST_SetSRID(ST_MakePoint(78.4138, 17.4849), 4326)::geography,
    'Kukatpally Y Junction Flyover Ramp, NH 65',
    'open',
    TRUE,
    84,
    'high',
    6,
    0,
    0,
    'pothole',
    0.94,
    TRUE,
    NOW() - INTERVAL '3 days',
    NOW() - INTERVAL '1 day'
),
-- 2. Broken Streetlight near Kukatpally Metro Station Pillar 812
(
    '11111111-0000-0000-0000-000000000002',
    '00000000-0000-0000-0000-000000000003',
    'streetlight',
    'Complete stretch of 4 streetlights dark between pillar 810 and 815. Dangerous for pedestrians at night.',
    ST_SetSRID(ST_MakePoint(78.4121, 17.4862), 4326)::geography,
    'Opposite Metro Pillar 812, Kukatpally Main Road',
    'open',
    FALSE,
    45,
    'medium',
    2,
    0,
    0,
    'streetlight',
    0.88,
    TRUE,
    NOW() - INTERVAL '5 days',
    NOW() - INTERVAL '2 days'
),
-- 3. Severe Road Break on Moosapet to Kukatpally stretch
(
    '11111111-0000-0000-0000-000000000003',
    '00000000-0000-0000-0000-000000000004',
    'road_break',
    'Large trench dug for water pipeline, filled with loose gravel and sinking. Two-wheelers losing balance.',
    ST_SetSRID(ST_MakePoint(78.4185, 17.4772), 4326)::geography,
    'Near Moosapet ' || 'X' || ' Road, towards Y Junction',
    'escalated',
    TRUE,
    92,
    'high',
    8,
    0,
    0,
    'road_break',
    0.91,
    TRUE,
    NOW() - INTERVAL '12 days',
    NOW() - INTERVAL '4 days'
),
-- 4. Blocked Footpath near KPHB Phase 1
(
    '11111111-0000-0000-0000-000000000004',
    '00000000-0000-0000-0000-000000000002',
    'footpath',
    'Construction debris and broken paving slabs blocking pedestrian path. Walkers forced onto busy traffic road.',
    ST_SetSRID(ST_MakePoint(78.4065, 17.4915), 4326)::geography,
    'Near KPHB Colony Phase 1 Main Entrance',
    'open',
    FALSE,
    55,
    'medium',
    2,
    0,
    0,
    'footpath',
    0.85,
    TRUE,
    NOW() - INTERVAL '6 days',
    NOW() - INTERVAL '3 days'
),
-- 5. Fixed Pothole on Balanagar Main Road
(
    '11111111-0000-0000-0000-000000000005',
    '00000000-0000-0000-0000-000000000003',
    'pothole',
    'Deep waterlogged pothole near bus shelter. Patch work completed by municipal workers.',
    ST_SetSRID(ST_MakePoint(78.4280, 17.4785), 4326)::geography,
    'Balanagar Main Road, Near IDPL Colony',
    'fixed',
    FALSE,
    30,
    'high',
    4,
    0,
    2,
    'pothole',
    0.82,
    TRUE,
    NOW() - INTERVAL '20 days',
    NOW() - INTERVAL '2 days'
),
-- 6. Open manhole / Other hazard near JNTU Metro
(
    '11111111-0000-0000-0000-000000000006',
    '00000000-0000-0000-0000-000000000004',
    'other',
    'Broken storm drain grating with sharp metal exposed. High risk for cyclists and two-wheelers.',
    ST_SetSRID(ST_MakePoint(78.3912, 17.4981), 4326)::geography,
    'JNTU College Metro Station Service Road',
    'open',
    TRUE,
    78,
    'high',
    5,
    0,
    0,
    'other',
    0.79,
    TRUE,
    NOW() - INTERVAL '4 days',
    NOW() - INTERVAL '1 day'
),
-- 7. Cluster of potholes on KPHB Road No 1
(
    '11111111-0000-0000-0000-000000000007',
    '00000000-0000-0000-0000-000000000002',
    'pothole',
    'Multiple potholes across both lanes right after the turning.',
    ST_SetSRID(ST_MakePoint(78.4010, 17.4930), 4326)::geography,
    'KPHB Road No 1, Near Rythu Bazar',
    'open',
    TRUE,
    72,
    'high',
    4,
    0,
    0,
    'pothole',
    0.89,
    TRUE,
    NOW() - INTERVAL '2 days',
    NOW() - INTERVAL '1 day'
),
-- 8. Broken streetlight near Vivekananda Nagar
(
    '11111111-0000-0000-0000-000000000008',
    '00000000-0000-0000-0000-000000000003',
    'streetlight',
    'Flickering and ungrounded streetlight pole sparking during rain.',
    ST_SetSRID(ST_MakePoint(78.4190, 17.4905), 4326)::geography,
    'Vivekananda Nagar Main Junction',
    'open',
    FALSE,
    48,
    'medium',
    2,
    0,
    0,
    'streetlight',
    0.86,
    TRUE,
    NOW() - INTERVAL '7 days',
    NOW() - INTERVAL '2 days'
),
-- 9. Road break on IDPL road
(
    '11111111-0000-0000-0000-000000000009',
    '00000000-0000-0000-0000-000000000004',
    'road_break',
    'Road cave-in near drainage junction, approximately 2 feet diameter.',
    ST_SetSRID(ST_MakePoint(78.4310, 17.4720), 4326)::geography,
    'IDPL Main Gate Road',
    'open',
    TRUE,
    76,
    'high',
    5,
    0,
    0,
    'road_break',
    0.93,
    TRUE,
    NOW() - INTERVAL '5 days',
    NOW() - INTERVAL '1 day'
),
-- 10. Fixed footpath blockage near Forum Mall / Nexus
(
    '11111111-0000-0000-0000-000000000010',
    '00000000-0000-0000-0000-000000000002',
    'footpath',
    'Illegal commercial hoardings removed from footpath.',
    ST_SetSRID(ST_MakePoint(78.3980, 17.4855), 4326)::geography,
    'Nexus Mall Road, KPHB',
    'fixed',
    FALSE,
    25,
    'high',
    3,
    0,
    2,
    'footpath',
    0.80,
    TRUE,
    NOW() - INTERVAL '15 days',
    NOW() - INTERVAL '1 day'
)
ON CONFLICT (id) DO UPDATE SET
    category = EXCLUDED.category,
    description = EXCLUDED.description,
    location = EXCLUDED.location,
    address_text = EXCLUDED.address_text,
    status = EXCLUDED.status,
    severity_score = EXCLUDED.severity_score,
    confirm_count = EXCLUDED.confirm_count,
    is_seed = TRUE;

-- ------------------------------------------------------------------------------
-- 3. Seed Verifications
-- ------------------------------------------------------------------------------
INSERT INTO public.verifications (report_id, user_id, vote, created_at)
VALUES
    ('11111111-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000003', 'confirm', NOW() - INTERVAL '2 days'),
    ('11111111-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000004', 'confirm', NOW() - INTERVAL '1 day'),
    ('11111111-0000-0000-0000-000000000005', '00000000-0000-0000-0000-000000000002', 'fixed', NOW() - INTERVAL '2 days'),
    ('11111111-0000-0000-0000-000000000005', '00000000-0000-0000-0000-000000000004', 'fixed', NOW() - INTERVAL '2 days')
ON CONFLICT (report_id, user_id, vote) DO NOTHING;

-- ------------------------------------------------------------------------------
-- 4. Seed Comments
-- ------------------------------------------------------------------------------
INSERT INTO public.comments (id, report_id, user_id, body, created_at)
VALUES
    ('22222222-0000-0000-0000-000000000001', '11111111-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000003', 'Hit this pothole yesterday evening in heavy rain. Please drive slowly!', NOW() - INTERVAL '2 days'),
    ('22222222-0000-0000-0000-000000000002', '11111111-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000004', 'Traffic police placed a temporary plastic barricade in the morning.', NOW() - INTERVAL '1 day'),
    ('22222222-0000-0000-0000-000000000003', '11111111-0000-0000-0000-000000000005', '00000000-0000-0000-0000-000000000002', 'GHMC road crew filled this up yesterday. Surface is now smooth.', NOW() - INTERVAL '2 days')
ON CONFLICT (id) DO NOTHING;

-- ------------------------------------------------------------------------------
-- 5. Seed Escalation for Report #3
-- ------------------------------------------------------------------------------
INSERT INTO public.escalations (id, report_id, escalated_by, authority_name, note, created_at)
VALUES (
    '33333333-0000-0000-0000-000000000001',
    '11111111-0000-0000-0000-000000000003',
    '00000000-0000-0000-0000-000000000001',
    'GHMC Kukatpally Engineering Division',
    'Escalated to Assistant City Planner due to acute risk to two-wheelers on NH 65 connector.',
    NOW() - INTERVAL '4 days'
) ON CONFLICT (id) DO NOTHING;
