#!/usr/bin/env python3
"""
Database Editor Script - Edit SQLite database directly
"""

import sqlite3
import os
from datetime import datetime

def edit_database():
    """Interactive database editor"""
    db_path = 'instance/calibration_app.db'
    
    if not os.path.exists(db_path):
        print("Database file not found!")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("=" * 50)
    print("Database Editor")
    print("=" * 50)
    
    while True:
        print("\nOptions:")
        print("1. View all calibration sessions")
        print("2. Add new calibration session")
        print("3. Update calibration session")
        print("4. Delete calibration session")
        print("5. View users")
        print("6. Delete user")
        print("7. Execute custom SQL")
        print("8. Exit")
        
        choice = input("\nEnter your choice (1-8): ").strip()
        
        if choice == '1':
            # View calibration sessions
            cursor.execute("""
                SELECT cs.id, u.email, cs.camera_id, cs.calibration_date, 
                       cs.status, cs.pdf_filename, cs.created_at
                FROM calibration_session cs
                JOIN user u ON cs.user_id = u.id
                ORDER BY cs.created_at DESC
            """)
            sessions = cursor.fetchall()
            
            print("\nCalibration Sessions:")
            print("-" * 80)
            for session in sessions:
                print(f"ID: {session[0]} | User: {session[1]} | Camera: {session[2]} | "
                      f"Date: {session[3]} | Status: {session[4]} | PDF: {session[5] or 'None'}")
        
        elif choice == '2':
            # Add new calibration session
            print("\nAdd New Calibration Session:")
            user_id = input("Lens ID: ").strip()
            camera_id = input("Vehicle ID: ").strip()
            calibration_date = input("Calibration Date (YYYY-MM-DD): ").strip()
            status = input("Status (pending/completed): ").strip()
            
            try:
                cursor.execute("""
                    INSERT INTO calibration_session (user_id, camera_id, calibration_date, status, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (user_id, camera_id, calibration_date, status, datetime.now()))
                conn.commit()
                print("✅ Calibration session added successfully!")
            except Exception as e:
                print(f"❌ Error: {e}")
        
        elif choice == '3':
            # Update calibration session
            session_id = input("Enter session ID to update: ").strip()
            
            print("Enter new values (press Enter to keep current):")
            camera_id = input("Vehicle ID: ").strip()
            status = input("Status: ").strip()
            pdf_filename = input("PDF filename: ").strip()
            
            try:
                updates = []
                params = []
                
                if camera_id:
                    updates.append("camera_id = ?")
                    params.append(camera_id)
                if status:
                    updates.append("status = ?")
                    params.append(status)
                if pdf_filename:
                    updates.append("pdf_filename = ?")
                    params.append(pdf_filename)
                
                if updates:
                    params.append(session_id)
                    query = f"UPDATE calibration_session SET {', '.join(updates)} WHERE id = ?"
                    cursor.execute(query, params)
                    conn.commit()
                    print("✅ Calibration session updated successfully!")
                else:
                    print("No changes made.")
            except Exception as e:
                print(f"❌ Error: {e}")
        
        elif choice == '4':
            # Delete calibration session
            session_id = input("Enter session ID to delete: ").strip()
            confirm = input(f"Are you sure you want to delete session {session_id}? (y/N): ").strip().lower()
            
            if confirm == 'y':
                try:
                    cursor.execute("DELETE FROM calibration_session WHERE id = ?", (session_id,))
                    conn.commit()
                    print("✅ Calibration session deleted successfully!")
                except Exception as e:
                    print(f"❌ Error: {e}")
            else:
                print("Deletion cancelled.")
        
        elif choice == '5':
            # View users
            cursor.execute("SELECT id, email, created_at FROM user")
            users = cursor.fetchall()
            
            print("\nUsers:")
            print("-" * 50)
            for user in users:
                print(f"ID: {user[0]} | Email: {user[1]} | Created: {user[2]}")
        
        elif choice == '6':
            # Delete user
            user_id = input("Enter lens ID to delete: ").strip()
            
            if not user_id:
                print("❌ Lens ID cannot be empty.")
                continue
            
            # First, show user info and related calibration sessions
            try:
                cursor.execute("SELECT id, email, created_at FROM user WHERE id = ?", (user_id,))
                user = cursor.fetchone()
                
                if not user:
                    print("❌ User not found.")
                    continue
                
                print(f"\nUser to delete:")
                print(f"ID: {user[0]} | Email: {user[1]} | Created: {user[2]}")
                
                # Check for related calibration sessions
                cursor.execute("SELECT COUNT(*) FROM calibration_session WHERE user_id = ?", (user_id,))
                session_count = cursor.fetchone()[0]
                
                if session_count > 0:
                    print(f"⚠️  This user has {session_count} calibration session(s) that will also be deleted.")
                    cursor.execute("SELECT id, camera_id, calibration_date, status FROM calibration_session WHERE user_id = ?", (user_id,))
                    sessions = cursor.fetchall()
                    print("Related calibration sessions:")
                    for session in sessions:
                        print(f"  - Session ID: {session[0]} | Camera: {session[1]} | Date: {session[2]} | Status: {session[3]}")
                
                confirm = input(f"\nAre you sure you want to delete user {user[1]} and all related data? (y/N): ").strip().lower()
                
                if confirm == 'y':
                    # Delete calibration sessions first (foreign key constraint)
                    cursor.execute("DELETE FROM calibration_session WHERE user_id = ?", (user_id,))
                    deleted_sessions = cursor.rowcount
                    
                    # Delete user
                    cursor.execute("DELETE FROM user WHERE id = ?", (user_id,))
                    deleted_user = cursor.rowcount
                    
                    if deleted_user > 0:
                        conn.commit()
                        print(f"✅ User deleted successfully!")
                        if deleted_sessions > 0:
                            print(f"✅ {deleted_sessions} related calibration session(s) also deleted.")
                    else:
                        print("❌ Failed to delete user.")
                else:
                    print("Deletion cancelled.")
                    
            except Exception as e:
                print(f"❌ Error: {e}")
        
        elif choice == '7':
            # Custom SQL
            sql = input("Enter SQL query: ").strip()
            try:
                cursor.execute(sql)
                if sql.upper().startswith('SELECT'):
                    results = cursor.fetchall()
                    for row in results:
                        print(row)
                else:
                    conn.commit()
                    print("✅ Query executed successfully!")
            except Exception as e:
                print(f"❌ Error: {e}")
        
        elif choice == '8':
            break
        
        else:
            print("Invalid choice. Please try again.")
    
    conn.close()
    print("\nDatabase connection closed.")

if __name__ == "__main__":
    edit_database()
