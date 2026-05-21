# src/clients/supabase_client.py
from supabase import create_client
from config.settings import SUPABASE_URL, SUPABASE_KEY

SUPABASE_CLIENT = create_client(SUPABASE_URL, SUPABASE_KEY)
