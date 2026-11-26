"""Comprehensive test suite for multi-role scheduling, unique role registration,
Combined Schedule, PA/SA synchronization, concurrency, and legacy migration safety.
"""

import os
import shutil
import sqlite3
import tempfile
import threading
import unittest
from datetime import date

# Point DATABASE_URL to an isolated temporary SQLite DB before importing app
_TEST_DIR = tempfile.mkdtemp(prefix='ceo_schedule_test_')
_TEST_DB_PATH = os.path.join(_TEST_DIR, 'test_schedule.db')
os.environ['DATABASE_URL'] = f'sqlite:///{_TEST_DB_PATH}'
os.environ['SECRET_KEY'] = 'test-secret-key'

from sqlalchemy.exc import IntegrityError  # noqa: E402
from app import app, db  # noqa: E402
from app.constants import DASHBOARD_TABS, DESIGNATED_POSITION_KEYS, NEW_UNIQUE_ROLES  # noqa: E402
from app.models.schedule import MeetingParticipant, ScheduleAuditLog, ScheduleEntry  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.schedule_sync import ensure_schema_and_backfill  # noqa: E402


class MultiRoleSchedulingTestCase(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        with app.app_context():
            db.session.remove()
            db.engine.dispose()
        shutil.rmtree(_TEST_DIR, ignore_errors=True)

    def setUp(self):
        app.config['TESTING'] = True
        with app.app_context():
            db.drop_all()
            ensure_schema_and_backfill()
            self._seed_base_users()
        self.client = app.test_client()

    def _seed_base_users(self):
        users = [
            User(name='Admin User', department='IT', designation='Admin', email='admin@corp.local', password='pw', role='Admin'),
            User(name='PA User', department='Mgmt', designation='PA', email='pa@corp.local', password='pw', role='Personal Assistant'),
            User(name='SA User', department='Mgmt', designation='SA', email='sa@corp.local', password='pw', role='Senior Assistant'),
            User(name='Proprietor Mam', department='Mgmt', designation='Proprietor', email='prop@corp.local', password='pw', role='Proprietor'),
            User(name='Emp One', department='Sales', designation='Exec', email='emp1@corp.local', password='pw', role='Employee'),
        ]
        db.session.add_all(users)
        db.session.commit()

    def _login(self, client, email, password='pw'):
        return client.post('/login', data={'email': email, 'password': password}, follow_redirects=True)

    def _register(self, client, name, email, role, password='pw'):
        return client.post(
            '/register',
            data={
                'name': name,
                'department': 'Ops',
                'designation': role,
                'email': email,
                'password': password,
                'role': role,
            },
            follow_redirects=True,
        )

    # ------------------------------------------------------------------
    # Test Case 1: Unique Role Registration (+ deactivation / reassignment)
    # ------------------------------------------------------------------
    def test_01_unique_role_registration_and_freeing(self):
        for idx, role in enumerate(NEW_UNIQUE_ROLES, start=1):
            # 1st registration succeeds
            res1 = self._register(self.client, f'First {role}', f'first{idx}@corp.local', role)
            self.assertIn(b'Registration successful', res1.data)

            # Registration page now shows this role as disabled/occupied
            reg_page = self.client.get('/register')
            self.assertIn(f'value="{role}" disabled'.encode(), reg_page.data)

            # 2nd registration is rejected by backend
            res2 = self._register(self.client, f'Second {role}', f'second{idx}@corp.local', role)
            self.assertIn(b'already assigned', res2.data)
            with app.app_context():
                self.assertEqual(User.query.filter_by(role=role, is_active=True).count(), 1)
                self.assertIsNone(User.query.filter_by(email=f'second{idx}@corp.local').first())

            # Database-level unique index directly blocks raw duplicate insert
            with app.app_context():
                dup = User(
                    name='Raw Dup',
                    department='Ops',
                    designation=role,
                    email=f'rawdup{idx}@corp.local',
                    password='pw',
                    role=role,
                    is_active=True,
                )
                db.session.add(dup)
                with self.assertRaises(IntegrityError):
                    db.session.commit()
                db.session.rollback()

        # Admin deactivates AGM user -> AGM becomes available again & deactivated user cannot log in
        self._login(self.client, 'admin@corp.local')
        with app.app_context():
            agm_user = User.query.filter_by(role='AGM').first()
            agm_id = agm_user.id
        res_toggle = self.client.post(f'/admin/users/{agm_id}/toggle-active', follow_redirects=True)
        self.assertIn(b'deactivated', res_toggle.data)
        self.client.get('/logout')

        bad_login = self._login(self.client, 'first1@corp.local')
        self.assertIn(b'deactivated', bad_login.data)

        res3 = self._register(self.client, 'Replacement AGM', 'new_agm@corp.local', 'AGM')
        self.assertIn(b'Registration successful', res3.data)

        # Admin reassigns Operation Manager -> Employee, freeing Operation Manager
        self._login(self.client, 'admin@corp.local')
        with app.app_context():
            op_user = User.query.filter_by(role='Operation Manager').first()
            op_id = op_user.id
        self.client.post(
            f'/admin/users/{op_id}/edit',
            data={
                'name': 'First Operation Manager',
                'department': 'Ops',
                'designation': 'Exec',
                'email': 'first2@corp.local',
                'phone_number': '',
                'role': 'Employee',
                'is_active': '1',
                'password': 'pw',
            },
            follow_redirects=True,
        )
        self.client.get('/logout')
        res4 = self._register(self.client, 'Replacement OpMgr', 'new_op@corp.local', 'Operation Manager')
        self.assertIn(b'Registration successful', res4.data)

    # ------------------------------------------------------------------
    # Test Case 2 & 3: Partial Multi-Role Meetings (AGM+OpMgr, CEO+HR)
    # ------------------------------------------------------------------
    def test_02_03_partial_multi_role_meetings_and_tab_order(self):
        self._register(self.client, 'AGM User', 'agm@corp.local', 'AGM')
        self._register(self.client, 'OpMgr User', 'op@corp.local', 'Operation Manager')
        self._register(self.client, 'HR User', 'hr@corp.local', 'HR Manager')

        # AGM creates meeting with AGM + Operation Manager
        self._login(self.client, 'agm@corp.local')
        today_str = date.today().strftime('%Y-%m-%d')
        self.client.post(
            '/admin/schedule/new',
            data={
                'event_date': today_str,
                'start_hour': '11',
                'start_minute': '00',
                'start_meridiem': 'AM',
                'end_hour': '12',
                'end_minute': '00',
                'end_meridiem': 'PM',
                'given_time': '1 hr',
                'activity': 'Production Review',
                'description': 'Daily production check',
                'location': 'Plant A',
                'responsible_person': 'AGM User',
                'meeting_type': 'Departmental',
                'priority': 'Normal',
                'status': 'Planned',
                'reschedule': 'NO',
                'positions': ['agm', 'operation_manager'],
            },
            follow_redirects=True,
        )

        # Verify exact 8-tab order inside the schedule-tabs-bar nav
        dash_agm = self.client.get('/dashboard?view_type=agm')
        html = dash_agm.data.decode('utf-8')
        tabs_start = html.index('class="schedule-tabs-bar"')
        tabs_end = html.index('</nav>', tabs_start)
        tabs_html = html[tabs_start:tabs_end]
        tab_positions = [tabs_html.index(label) for _, label in DASHBOARD_TABS]
        self.assertEqual(tab_positions, sorted(tab_positions))

        # Visible in AGM, Operation Manager, AGM's My Schedule, OpMgr's My Schedule; NOT in Combined or CEO
        self.assertIn('Production Review', html)
        self.assertIn('Production Review', self.client.get('/dashboard?view_type=operation_manager').data.decode('utf-8'))
        self.assertIn('Production Review', self.client.get('/dashboard?view_type=mine').data.decode('utf-8'))
        self.assertNotIn('Production Review', self.client.get('/dashboard?view_type=combined').data.decode('utf-8'))
        self.assertNotIn('Production Review', self.client.get('/dashboard?view_type=ceo').data.decode('utf-8'))

        # OpMgr logs in and sees it in My Schedule
        self.client.get('/logout')
        self._login(self.client, 'op@corp.local')
        self.assertIn('Production Review', self.client.get('/dashboard?view_type=mine').data.decode('utf-8'))

        # PA creates CEO + HR Manager meeting
        self.client.get('/logout')
        self._login(self.client, 'pa@corp.local')
        self.client.post(
            '/admin/schedule/new',
            data={
                'event_date': today_str,
                'start_hour': '03',
                'start_minute': '00',
                'start_meridiem': 'PM',
                'end_hour': '04',
                'end_minute': '00',
                'end_meridiem': 'PM',
                'activity': 'HR Department Discussion',
                'location': 'CEO Office',
                'responsible_person': 'CEO Sir',
                'priority': 'Normal',
                'status': 'Planned',
                'reschedule': 'NO',
                'positions': ['ceo', 'hr_manager'],
            },
            follow_redirects=True,
        )
        self.assertIn('HR Department Discussion', self.client.get('/dashboard?view_type=ceo').data.decode('utf-8'))
        self.assertIn('HR Department Discussion', self.client.get('/dashboard?view_type=hr_manager').data.decode('utf-8'))
        self.assertNotIn('HR Department Discussion', self.client.get('/dashboard?view_type=combined').data.decode('utf-8'))
        # Creator (PA) is NOT automatically added to PA's My Schedule
        self.assertNotIn('HR Department Discussion', self.client.get('/dashboard?view_type=mine').data.decode('utf-8'))

    # ------------------------------------------------------------------
    # Test Case 4, 5, 6, 7, 8: Combined Meeting, PA/SA Sync, Modify, Cancel
    # ------------------------------------------------------------------
    def test_04_05_06_07_08_combined_pa_sa_modify_and_cancel(self):
        self._register(self.client, 'AGM User', 'agm@corp.local', 'AGM')
        self._register(self.client, 'OpMgr User', 'op@corp.local', 'Operation Manager')
        self._register(self.client, 'AIC User', 'aic@corp.local', 'Admin In Charge')
        self._register(self.client, 'HR User', 'hr@corp.local', 'HR Manager')

        today_str = date.today().strftime('%Y-%m-%d')

        # Test Case 5: PA creates meeting for CEO + Proprietor + AGM
        self._login(self.client, 'pa@corp.local')
        self.client.post(
            '/admin/schedule/new',
            data={
                'event_date': today_str,
                'start_hour': '10',
                'start_minute': '00',
                'start_meridiem': 'AM',
                'end_hour': '11',
                'end_minute': '00',
                'end_meridiem': 'AM',
                'activity': 'PA Tri-Party Sync',
                'location': 'Boardroom',
                'responsible_person': 'CEO Sir',
                'priority': 'Urgent',
                'status': 'Planned',
                'reschedule': 'NO',
                'positions': ['ceo', 'proprietor', 'agm'],
            },
            follow_redirects=True,
        )
        for vt in ['ceo', 'proprietor', 'agm']:
            self.assertIn('PA Tri-Party Sync', self.client.get(f'/dashboard?view_type={vt}').data.decode('utf-8'))
        self.assertNotIn('PA Tri-Party Sync', self.client.get('/dashboard?view_type=combined').data.decode('utf-8'))

        # Test Case 4 & 6: Senior Assistant creates 6-position Combined meeting
        self.client.get('/logout')
        self._login(self.client, 'sa@corp.local')
        self.client.post(
            '/admin/schedule/new',
            data={
                'event_date': today_str,
                'start_hour': '02',
                'start_minute': '00',
                'start_meridiem': 'PM',
                'end_hour': '03',
                'end_minute': '30',
                'end_meridiem': 'PM',
                'activity': 'Monthly Management Review',
                'description': 'All 6 leaders quarterly/monthly sync',
                'location': 'Main Conference Hall',
                'responsible_person': 'CEO Sir',
                'meeting_type': 'Management Review',
                'priority': 'Urgent',
                'status': 'Planned',
                'notes': 'Bring department KPIs',
                'reschedule': 'NO',
                'positions': DESIGNATED_POSITION_KEYS,
            },
            follow_redirects=True,
        )

        # Single central ScheduleEntry row, visible in all 6 + Combined
        with app.app_context():
            matching = ScheduleEntry.query.filter_by(activity='Monthly Management Review').all()
            self.assertEqual(len(matching), 1)
            entry_id = matching[0].id
            self.assertTrue(matching[0].is_combined_meeting)
            self.assertEqual(matching[0].creator.email, 'sa@corp.local')

        for vt in DESIGNATED_POSITION_KEYS + ['combined']:
            self.assertIn('Monthly Management Review', self.client.get(f'/dashboard?view_type={vt}').data.decode('utf-8'))

        # Test Case 7: Modify date, time, and remove HR Manager -> disappears from HR Manager & Combined!
        self.client.post(
            f'/admin/schedule/{entry_id}/edit',
            data={
                'event_date': today_str,
                'start_hour': '04',
                'start_minute': '00',
                'start_meridiem': 'PM',
                'end_hour': '05',
                'end_minute': '00',
                'end_meridiem': 'PM',
                'activity': 'Monthly Management Review Updated',
                'location': 'Main Conference Hall',
                'responsible_person': 'CEO Sir',
                'priority': 'Urgent',
                'status': 'Rescheduled',
                'reschedule': 'YES',
                'positions': ['ceo', 'proprietor', 'agm', 'operation_manager', 'admin_in_charge'],
            },
            follow_redirects=True,
        )

        for vt in ['ceo', 'proprietor', 'agm', 'operation_manager', 'admin_in_charge']:
            body = self.client.get(f'/dashboard?view_type={vt}').data.decode('utf-8')
            self.assertIn('Monthly Management Review Updated', body)
            self.assertIn('04:00 PM - 05:00 PM', body)
        self.assertNotIn('Monthly Management Review Updated', self.client.get('/dashboard?view_type=hr_manager').data.decode('utf-8'))
        self.assertNotIn('Monthly Management Review Updated', self.client.get('/dashboard?view_type=combined').data.decode('utf-8'))

        # Re-add HR Manager via inline AJAX endpoint -> reappears in HR Manager & Combined!
        resp = self.client.post(f'/schedule/{entry_id}/toggle-position/hr_manager')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()['is_combined'])
        self.assertIn('Monthly Management Review Updated', self.client.get('/dashboard?view_type=combined').data.decode('utf-8'))

        # Test Case 8: Cancel / Delete common meeting -> disappears everywhere
        self.client.get(f'/admin/schedule/{entry_id}/delete', follow_redirects=True)
        for vt in DESIGNATED_POSITION_KEYS + ['combined']:
            self.assertNotIn('Monthly Management Review Updated', self.client.get(f'/dashboard?view_type={vt}').data.decode('utf-8'))

        # Audit log preserved delete record
        with app.app_context():
            logs = ScheduleAuditLog.query.filter_by(action='deleted', entry_snapshot_title='Monthly Management Review Updated').all()
            self.assertEqual(len(logs), 1)

    # ------------------------------------------------------------------
    # Test Case 9: Existing Employee / Admin / PA Permission Boundaries
    # ------------------------------------------------------------------
    def test_09_existing_functionality_and_permissions(self):
        today_str = date.today().strftime('%Y-%m-%d')

        # PA cannot access Admin-only User Management
        self._login(self.client, 'pa@corp.local')
        res_pa_users = self.client.get('/admin/users', follow_redirects=True)
        self.assertIn(b'Only the Admin can manage users', res_pa_users.data)
        self.client.get('/logout')

        # Employee creates personal schedule
        self._login(self.client, 'emp1@corp.local')
        self.client.post(
            '/schedule/new',
            data={
                'event_date': today_str,
                'start_hour': '09',
                'start_minute': '30',
                'start_meridiem': 'AM',
                'end_hour': '10',
                'end_minute': '30',
                'end_meridiem': 'AM',
                'activity': 'Employee Field Visit',
                'location': 'Client Site',
                'priority': 'Normal',
                'status': 'Planned',
                'reschedule': 'NO',
            },
            follow_redirects=True,
        )
        self.assertIn('Employee Field Visit', self.client.get('/dashboard?view_type=mine').data.decode('utf-8'))
        self.assertNotIn('Employee Field Visit', self.client.get('/dashboard?view_type=ceo').data.decode('utf-8'))

        # Employee cannot access management /admin/schedule/new
        res_emp_admin = self.client.get('/admin/schedule/new', follow_redirects=True)
        self.assertIn(b'Only authorized staff or designated role holders', res_emp_admin.data)

    # ------------------------------------------------------------------
    # Test Case 10: Concurrent Updates & Duplicate Prevention
    # ------------------------------------------------------------------
    def test_10_concurrent_participant_updates(self):
        self._register(self.client, 'AGM User', 'agm@corp.local', 'AGM')
        today_str = date.today().strftime('%Y-%m-%d')
        self._login(self.client, 'pa@corp.local')
        self.client.post(
            '/admin/schedule/new',
            data={
                'event_date': today_str,
                'start_hour': '11',
                'start_minute': '00',
                'start_meridiem': 'AM',
                'end_hour': '12',
                'end_minute': '00',
                'end_meridiem': 'PM',
                'activity': 'Concurrent Meeting',
                'location': 'Room 1',
                'responsible_person': 'CEO Sir',
                'priority': 'Normal',
                'status': 'Planned',
                'reschedule': 'NO',
                'positions': ['ceo', 'ceo', 'agm'],  # duplicate position in payload
            },
            follow_redirects=True,
        )

        with app.app_context():
            entry = ScheduleEntry.query.filter_by(activity='Concurrent Meeting').first()
            self.assertIsNotNone(entry)
            self.assertEqual(len(entry.participants), 2)
            entry_id = entry.id

            # DB unique index blocks duplicate position insertion on same entry
            dup_mp = MeetingParticipant(schedule_entry_id=entry_id, position_key='ceo')
            db.session.add(dup_mp)
            with self.assertRaises(IntegrityError):
                db.session.commit()
            db.session.rollback()

        # Concurrent requests from two clients updating the same meeting
        c1 = app.test_client()
        c2 = app.test_client()
        self._login(c1, 'pa@corp.local')
        self._login(c2, 'sa@corp.local')
        errors = []

        def worker(cli, positions):
            try:
                resp = cli.post(
                    f'/admin/schedule/{entry_id}/edit',
                    data={
                        'event_date': today_str,
                        'start_hour': '11',
                        'start_minute': '00',
                        'start_meridiem': 'AM',
                        'end_hour': '12',
                        'end_minute': '00',
                        'end_meridiem': 'PM',
                        'activity': 'Concurrent Meeting',
                        'location': 'Room 1',
                        'responsible_person': 'CEO Sir',
                        'priority': 'Normal',
                        'status': 'Planned',
                        'reschedule': 'NO',
                        'positions': positions,
                    },
                    follow_redirects=True,
                )
                if resp.status_code >= 500:
                    errors.append(resp.status_code)
            except Exception as exc:
                errors.append(str(exc))

        t1 = threading.Thread(target=worker, args=(c1, ['ceo', 'agm', 'hr_manager']))
        t2 = threading.Thread(target=worker, args=(c2, ['ceo', 'agm', 'proprietor']))
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        self.assertEqual(errors, [])

        with app.app_context():
            parts = MeetingParticipant.query.filter_by(schedule_entry_id=entry_id).all()
            pos_keys = [p.position_key for p in parts if p.position_key]
            self.assertEqual(len(pos_keys), len(set(pos_keys)))

    # ------------------------------------------------------------------
    # Legacy Data Backfill Safety Test
    # ------------------------------------------------------------------
    def test_11_legacy_backfill_preserves_old_records(self):
        with app.app_context():
            prop = User.query.filter_by(role='Proprietor').first()
            emp = User.query.filter_by(role='Employee').first()
            ceo_legacy = ScheduleEntry(
                event_date=date.today(),
                time='10:00 AM - 11:00 AM',
                activity='Legacy CEO Activity',
                location='HQ',
                responsible_person='CEO Sir',
                schedule_type='ceo',
                user_id=None,
            )
            # Simulate legacy bug where Proprietor was in attendants of a CEO event
            ceo_legacy.attendants = [prop, emp]
            prop_legacy = ScheduleEntry(
                event_date=date.today(),
                time='02:00 PM - 03:00 PM',
                activity='Legacy Proprietor Activity',
                location='HQ',
                responsible_person='Proprietor Mam',
                schedule_type='proprietor',
                user_id=prop.id,
            )
            db.session.add_all([ceo_legacy, prop_legacy])
            db.session.commit()

            ensure_schema_and_backfill()

        self._login(self.client, 'pa@corp.local')
        ceo_html = self.client.get('/dashboard?view_type=ceo').data.decode('utf-8')
        prop_html = self.client.get('/dashboard?view_type=proprietor').data.decode('utf-8')
        self.assertIn('Legacy CEO Activity', ceo_html)
        self.assertNotIn('Legacy CEO Activity', prop_html)
        self.assertIn('Legacy Proprietor Activity', prop_html)
        self.assertNotIn('Legacy Proprietor Activity', ceo_html)

    def test_12_concurrent_unique_role_registration_and_permission_isolation(self):
        # Concurrent registration race for HR Manager
        c1 = app.test_client()
        c2 = app.test_client()
        results = []

        def reg_worker(cli, idx):
            r = self._register(cli, f'HR {idx}', f'hr{idx}@corp.local', 'HR Manager')
            results.append(r.status_code)

        t1 = threading.Thread(target=reg_worker, args=(c1, 1))
        t2 = threading.Thread(target=reg_worker, args=(c2, 2))
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        self.assertTrue(all(code < 500 for code in results))
        with app.app_context():
            self.assertEqual(User.query.filter_by(role='HR Manager', is_active=True).count(), 1)

        # AGM cannot edit or delete a CEO-only meeting created by PA
        self._register(self.client, 'AGM User', 'agm_iso@corp.local', 'AGM')
        self._login(self.client, 'pa@corp.local')
        self.client.post(
            '/admin/schedule/new',
            data={
                'event_date': date.today().strftime('%Y-%m-%d'),
                'start_hour': '09',
                'start_minute': '00',
                'start_meridiem': 'AM',
                'end_hour': '10',
                'end_minute': '00',
                'end_meridiem': 'AM',
                'activity': 'CEO Private Briefing',
                'location': 'CEO Cabin',
                'responsible_person': 'CEO Sir',
                'priority': 'Confidential',
                'status': 'Planned',
                'reschedule': 'NO',
                'positions': ['ceo'],
            },
            follow_redirects=True,
        )
        with app.app_context():
            ceo_entry = ScheduleEntry.query.filter_by(activity='CEO Private Briefing').first()
            ceo_entry_id = ceo_entry.id

        self.client.get('/logout')
        self._login(self.client, 'agm_iso@corp.local')
        edit_res = self.client.post(
            f'/admin/schedule/{ceo_entry_id}/edit',
            data={'activity': 'Hacked'},
            follow_redirects=True,
        )
        self.assertIn(b'do not have permission', edit_res.data)
        del_res = self.client.get(f'/admin/schedule/{ceo_entry_id}/delete', follow_redirects=True)
        self.assertIn(b'do not have permission', del_res.data)
        with app.app_context():
            self.assertEqual(ScheduleEntry.query.get(ceo_entry_id).activity, 'CEO Private Briefing')


if __name__ == '__main__':
    unittest.main(verbosity=2)
