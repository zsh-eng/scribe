// src/lib/supabase.ts
import { createClient } from '@supabase/supabase-js'

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!
const supabasePublishableKey = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY!

// Client for frontend (uses publishable key)
export const supabase = createClient(supabaseUrl, supabasePublishableKey)

// Admin client for server-side (uses secret key)
export const supabaseAdmin = createClient(
    supabaseUrl,
    process.env.SUPABASE_SECRET_KEY!,
    {
        auth: {
            autoRefreshToken: false,
            persistSession: false
        }
    }
)