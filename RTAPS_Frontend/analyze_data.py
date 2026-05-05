#!/usr/bin/env python3
"""
RTAPS Data Analysis Script
Reads and analyzes rtaps_users and rtaps_sessions CSV files
"""

import pandas as pd
import os
import sys
import json
import re
from pathlib import Path
from datetime import datetime

def read_csv_file(file_path):
    """Read a CSV file and return a DataFrame"""
    try:
        df = pd.read_csv(file_path)
        print(f"\n✓ Successfully loaded: {file_path}")
        print(f"  Shape: {df.shape[0]} rows × {df.shape[1]} columns")
        return df
    except FileNotFoundError:
        print(f"\n✗ File not found: {file_path}")
        return None
    except Exception as e:
        print(f"\n✗ Error reading {file_path}: {str(e)}")
        return None

def parse_dynamodb_value(value):
    """Parse DynamoDB formatted value recursively"""
    if isinstance(value, dict):
        if 'N' in value:
            try:
                return int(value['N'])
            except (ValueError, TypeError):
                try:
                    return float(value['N'])
                except (ValueError, TypeError):
                    return value['N']
        elif 'S' in value:
            return value['S']
        elif 'BOOL' in value:
            return value['BOOL']
        elif 'M' in value:
            # Recursively parse map values
            return {k: parse_dynamodb_value(v) for k, v in value['M'].items()}
        elif 'L' in value:
            # Handle lists
            return [parse_dynamodb_value(item) for item in value['L']]
    return value

def parse_steps_json(steps_str):
    """Parse the steps JSON string from DynamoDB format"""
    if pd.isna(steps_str) or steps_str == '':
        return []
    try:
        steps_list = json.loads(steps_str)
        parsed_steps = []
        for step in steps_list:
            # Parse the entire step object (which contains 'M' key)
            parsed_step = parse_dynamodb_value(step)
            parsed_steps.append(parsed_step)
        return parsed_steps
    except (json.JSONDecodeError, TypeError) as e:
        print(f"  Warning: Could not parse steps JSON: {e}")
        return []

def display_dataframe_info(df, name):
    """Display basic information about a DataFrame"""
    if df is None:
        return
    
    print(f"\n{'='*60}")
    print(f"DataFrame: {name}")
    print(f"{'='*60}")
    
    print(f"\nColumn names ({len(df.columns)}):")
    for i, col in enumerate(df.columns, 1):
        print(f"  {i}. {col}")
    
    print(f"\nFirst few rows:")
    print(df.head())
    
    print(f"\nData types:")
    print(df.dtypes)
    
    print(f"\nBasic statistics:")
    print(df.describe())
    
    print(f"\nMissing values:")
    missing = df.isnull().sum()
    if missing.sum() > 0:
        print(missing[missing > 0])
    else:
        print("  No missing values")
    
    # Special handling for sessions dataframe - show parsed steps sample
    if name == "rtaps_sessions" and 'steps' in df.columns:
        print(f"\n{'='*60}")
        print("Sample Parsed Steps Data:")
        print(f"{'='*60}")
        non_null_steps = df[df['steps'].notna()]['steps']
        if len(non_null_steps) > 0:
            sample_steps = parse_steps_json(non_null_steps.iloc[0])
            if sample_steps:
                print(f"\nFirst session has {len(sample_steps)} steps:")
                for i, step in enumerate(sample_steps[:3], 1):  # Show first 3 steps
                    print(f"\n  Step {i}:")
                    for key, value in step.items():
                        print(f"    {key}: {value}")
                if len(sample_steps) > 3:
                    print(f"\n  ... and {len(sample_steps) - 3} more steps")

def classify_user_type(username):
    """Classify user as expert or novice based on username pattern"""
    if pd.isna(username):
        return None
    
    username_str = str(username)
    # Expert: user_* (e.g., user_31, user_34)
    if re.match(r'^user_\d+$', username_str):
        return 'expert'
    # Novice: user followed by number only (e.g., user11, user12, user13)
    elif re.match(r'^user\d+$', username_str):
        return 'novice'
    else:
        return None

def analyze_user_times(users_df, sessions_df):
    """Analyze user times for December 4th, filtering by user* usernames"""
    print(f"\n{'='*60}")
    print("User Time Analysis - December 4th")
    print(f"{'='*60}")
    
    # Convert completedAt to datetime
    sessions_df['completedAt_dt'] = pd.to_datetime(sessions_df['completedAt'], errors='coerce')
    
    # Filter for December 4th, 2025
    dec_4_sessions = sessions_df[
        (sessions_df['completedAt_dt'].dt.year == 2025) &
        (sessions_df['completedAt_dt'].dt.month == 12) &
        (sessions_df['completedAt_dt'].dt.day == 4)
    ].copy()
    
    print(f"\nSessions on December 4th, 2025: {len(dec_4_sessions)}")
    
    if len(dec_4_sessions) == 0:
        print("No sessions found for December 4th, 2025")
        return
    
    # Merge with users to get usernames
    # First, we need to match participantId or participantUsername with userId or username
    merged = dec_4_sessions.merge(
        users_df,
        left_on='participantId',
        right_on='userId',
        how='left'
    )
    
    # If participantId didn't match, try participantUsername
    unmatched = merged[merged['username'].isna()]
    if len(unmatched) > 0:
        merged_unmatched = unmatched.merge(
            users_df,
            left_on='participantUsername',
            right_on='username',
            how='left',
            suffixes=('', '_alt')
        )
        # Update the merged dataframe
        for idx in merged_unmatched.index:
            if pd.notna(merged_unmatched.loc[idx, 'username_alt']):
                merged.loc[idx, 'username'] = merged_unmatched.loc[idx, 'username_alt']
                merged.loc[idx, 'userId'] = merged_unmatched.loc[idx, 'userId_alt']
    
    # Filter for usernames starting with "user"
    user_sessions = merged[merged['username'].str.startswith('user', na=False)].copy()
    
    print(f"Sessions with usernames starting with 'user': {len(user_sessions)}")
    
    if len(user_sessions) == 0:
        print("No sessions found with usernames starting with 'user'")
        return
    
    # Classify users
    user_sessions['userType'] = user_sessions['username'].apply(classify_user_type)
    
    # Filter out None classifications (usernames that don't match our patterns)
    user_sessions = user_sessions[user_sessions['userType'].notna()].copy()
    
    print(f"Sessions after classification: {len(user_sessions)}")
    
    # Group by user, procedure, and calculate time per user per procedure
    user_procedure_times = user_sessions.groupby(['username', 'userType', 'procedureId', 'procedureName']).agg({
        'totalTimeSec': 'sum',  # Sum of all session times for each user per procedure
        'sessionId': 'count'   # Count of sessions per user per procedure
    }).reset_index()
    user_procedure_times.columns = ['username', 'userType', 'procedureId', 'procedureName', 'totalTimeSec', 'sessionCount']
    
    # Also calculate total time per user (across all procedures) for averages
    user_times = user_sessions.groupby(['username', 'userType']).agg({
        'totalTimeSec': 'sum',  # Sum of all session times for each user
        'sessionId': 'count'   # Count of sessions per user
    }).reset_index()
    user_times.columns = ['username', 'userType', 'totalTimeSec', 'sessionCount']
    
    print(f"\n{'='*60}")
    print("Time per User per Procedure:")
    print(f"{'='*60}")
    
    # Separate by user type first
    for user_type in ['expert', 'novice']:
        type_label = "Experts (user_*)" if user_type == 'expert' else "Novices (user followed by number)"
        print(f"\n{'='*60}")
        print(f"{type_label}")
        print(f"{'='*60}")
        
        # Get users of this type
        type_users = user_times[user_times['userType'] == user_type].sort_values('username')
        
        if len(type_users) == 0:
            print(f"\nNo {user_type} users found")
            continue
        
        # Group by procedure for this user type
        type_procedure_data = user_procedure_times[user_procedure_times['userType'] == user_type]
        
        # Get unique procedures for this type
        procedures = type_procedure_data.groupby(['procedureId', 'procedureName']).first().reset_index()
        procedures = procedures.sort_values('procedureId')
        
        # For each procedure, show all users
        for _, proc_row in procedures.iterrows():
            proc_id = proc_row['procedureId']
            proc_name = str(proc_row['procedureName']) if pd.notna(proc_row['procedureName']) else f"Procedure {int(proc_id)}"
            
            print(f"\n{proc_name}:")
            print(f"  {'Username':<20} {'Time (sec)':<15} {'Sessions':<10}")
            print(f"  {'-'*45}")
            
            # Get all users who did this procedure
            proc_users = type_procedure_data[
                (type_procedure_data['procedureId'] == proc_id)
            ].sort_values('username')
            
            for _, user_proc_row in proc_users.iterrows():
                username = user_proc_row['username']
                print(f"  {username:<20} {user_proc_row['totalTimeSec']:<15} {user_proc_row['sessionCount']:<10}")
    
    # Calculate averages per procedure for experts and novices
    print(f"\n{'='*60}")
    print("Average Times by Procedure:")
    print(f"{'='*60}")
    
    # Get unique procedures for experts and novices separately
    expert_procedures = user_procedure_times[user_procedure_times['userType'] == 'expert'].groupby(['procedureId', 'procedureName']).first().reset_index()
    expert_procedures = expert_procedures.sort_values('procedureId')
    
    novice_procedures = user_procedure_times[user_procedure_times['userType'] == 'novice'].groupby(['procedureId', 'procedureName']).first().reset_index()
    novice_procedures = novice_procedures.sort_values('procedureId')
    
    # Get all unique procedure IDs (same procedure type, different trains)
    all_proc_ids = sorted(set(user_procedure_times['procedureId'].unique()))
    
    print(f"\n{'Procedure':<35} {'Experts Avg (sec)':<20} {'Novices Avg (sec)':<20}")
    print("-" * 75)
    
    for proc_id in all_proc_ids:
        # Get procedure names for experts and novices (they may have different train numbers)
        expert_proc = expert_procedures[expert_procedures['procedureId'] == proc_id]
        novice_proc = novice_procedures[novice_procedures['procedureId'] == proc_id]
        
        # Expert average for this procedure
        expert_proc_times = user_procedure_times[
            (user_procedure_times['userType'] == 'expert') &
            (user_procedure_times['procedureId'] == proc_id)
        ]['totalTimeSec']
        expert_avg = expert_proc_times.mean() if len(expert_proc_times) > 0 else None
        
        # Novice average for this procedure
        novice_proc_times = user_procedure_times[
            (user_procedure_times['userType'] == 'novice') &
            (user_procedure_times['procedureId'] == proc_id)
        ]['totalTimeSec']
        novice_avg = novice_proc_times.mean() if len(novice_proc_times) > 0 else None
        
        # Show procedure name - use expert's name if available, otherwise novice's
        if len(expert_proc) > 0:
            expert_proc_name = str(expert_proc.iloc[0]['procedureName']) if pd.notna(expert_proc.iloc[0]['procedureName']) else f"Procedure {int(proc_id)}"
        else:
            expert_proc_name = f"Procedure {int(proc_id)}"
            
        if len(novice_proc) > 0:
            novice_proc_name = str(novice_proc.iloc[0]['procedureName']) if pd.notna(novice_proc.iloc[0]['procedureName']) else f"Procedure {int(proc_id)}"
        else:
            novice_proc_name = f"Procedure {int(proc_id)}"
        
        # Extract base procedure name (without train number) for display
        if ' - Train' in expert_proc_name:
            base_name = expert_proc_name.split(' - Train')[0]
        elif ' - Train' in novice_proc_name:
            base_name = novice_proc_name.split(' - Train')[0]
        else:
            base_name = expert_proc_name if len(expert_proc) > 0 else novice_proc_name
        
        expert_str = f"{expert_avg:.2f}" if expert_avg is not None else "N/A"
        novice_str = f"{novice_avg:.2f}" if novice_avg is not None else "N/A"
        
        print(f"{base_name:<35} {expert_str:<20} {novice_str:<20}")
    
    # Overall averages
    print(f"\n{'='*60}")
    print("Overall Average Times:")
    print(f"{'='*60}")
    
    expert_times = user_times[user_times['userType'] == 'expert']['totalTimeSec']
    novice_times = user_times[user_times['userType'] == 'novice']['totalTimeSec']
    
    if len(expert_times) > 0:
        expert_avg = expert_times.mean()
        expert_count = len(expert_times)
        print(f"\nExperts (user_*):")
        print(f"  Number of users: {expert_count}")
        print(f"  Average total time: {expert_avg:.2f} seconds ({expert_avg/60:.2f} minutes)")
        print(f"  Min: {expert_times.min():.2f} sec, Max: {expert_times.max():.2f} sec")
    else:
        print("\nExperts: No data found")
    
    if len(novice_times) > 0:
        novice_avg = novice_times.mean()
        novice_count = len(novice_times)
        print(f"\nNovices (user followed by number):")
        print(f"  Number of users: {novice_count}")
        print(f"  Average total time: {novice_avg:.2f} seconds ({novice_avg/60:.2f} minutes)")
        print(f"  Min: {novice_times.min():.2f} sec, Max: {novice_times.max():.2f} sec")
    else:
        print("\nNovices: No data found")
    
    return user_times

def main():
    # Look for CSV files in common locations
    workspace = Path(__file__).parent
    possible_locations = [
        workspace / "data",  # Check data/ first
        workspace,
        workspace / "csv",
        Path.home() / "Downloads",
    ]
    
    # Try to find the CSV files
    users_file = None
    sessions_file = None
    
    # First, check if files are provided as command line arguments
    if len(sys.argv) >= 3:
        users_file = sys.argv[1]
        sessions_file = sys.argv[2]
    else:
        # Search for files
        for location in possible_locations:
            users_path = location / "rtaps_users.csv"
            sessions_path = location / "rtaps_sessions.csv"
            
            if users_path.exists() and users_file is None:
                users_file = str(users_path)
            if sessions_path.exists() and sessions_file is None:
                sessions_file = str(sessions_path)
    
    # If still not found, ask user
    if not users_file:
        users_file = input("Enter path to rtaps_users.csv (or press Enter to skip): ").strip()
        if not users_file:
            users_file = None
    
    if not sessions_file:
        sessions_file = input("Enter path to rtaps_sessions.csv (or press Enter to skip): ").strip()
        if not sessions_file:
            sessions_file = None
    
    # Read the CSV files
    users_df = None
    sessions_df = None
    
    if users_file:
        users_df = read_csv_file(users_file)
        if users_df is not None:
            display_dataframe_info(users_df, "rtaps_users")
    
    if sessions_file:
        sessions_df = read_csv_file(sessions_file)
        if sessions_df is not None:
            display_dataframe_info(sessions_df, "rtaps_sessions")
    
    # Perform user time analysis
    if users_df is not None and sessions_df is not None:
        user_times = analyze_user_times(users_df, sessions_df)
        return users_df, sessions_df, user_times
    
    # Return the dataframes for further analysis
    return users_df, sessions_df, None

if __name__ == "__main__":
    users_df, sessions_df, user_times = main()
    
    if users_df is None and sessions_df is None:
        print("\n⚠ No data loaded. Please provide the CSV file paths.")
        print("\nUsage:")
        print("  python analyze_data.py [path_to_rtaps_users.csv] [path_to_rtaps_sessions.csv]")
        print("\nOr place the CSV files in one of these locations:")
        print("  - Current directory")
        print("  - ./data/")
        print("  - ./csv/")
        print("  - ~/Downloads/")

