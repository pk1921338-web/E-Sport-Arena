from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, login_user, logout_user,
    login_required, current_user, UserMixin
)
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta


app = Flask(__name__)
app.config['SECRET_KEY'] = 'change-this-secret-key'

# PostgreSQL database (Render Postgres)
app.config['SQLALCHEMY_DATABASE_URI'] = (
    'postgresql://esport_arena_db_user:'
    'IhrG2vB8YZYQyKqRu6zulfJ61zP7uxC1'
    '@dpg-d56lljbuibrs739ml060-a/esport_arena_db'
)

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Session ko bahut lamba (20 saal) bana do
app.permanent_session_lifetime = timedelta(days=365 * 20)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'


# Har request se pehle session permanent set karo
@app.before_request
def make_session_permanent():
    session.permanent = True


# ------------- MODELS -------------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    player_id = db.Column(db.String(50))
    winning_balance = db.Column(db.Float, default=0.0)
    added_balance = db.Column(db.Float, default=0.0)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class AddRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    amount = db.Column(db.Float)
    upi_id = db.Column(db.String(100))
    txn_id = db.Column(db.String(100))
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class WithdrawRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    amount = db.Column(db.Float)
    upi_id = db.Column(db.String(100))
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Tournament(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    game = db.Column(db.String(50), nullable=False)
    mode = db.Column(db.String(20), nullable=False)
    entry_fee = db.Column(db.Float, nullable=False)
    prize_pool = db.Column(db.Float, nullable=False)
    max_slots = db.Column(db.Integer, nullable=False)
    filled_slots = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default='upcoming')  # upcoming / live / finished
    start_time = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    winner_note = db.Column(db.Text)
    room_id = db.Column(db.String(50))
    room_pass = db.Column(db.String(50))
    admin_note = db.Column(db.Text)
    # NEW: monthly grand flag
    is_grand = db.Column(db.Boolean, default=False)


class TournamentJoin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournament.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    in_game_name = db.Column(db.String(100))
    in_game_uid = db.Column(db.String(50))
    slot = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ------------- ROUTES -------------
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form['email'].strip()
        password = request.form['password']
        player_id = request.form['player_id'].strip()

        if User.query.filter_by(email=email).first():
            flash('Email already exists.')
            return redirect(url_for('signup'))

        user = User(
            email=email,
            player_id=player_id,
            password_hash=generate_password_hash(password)
        )
        db.session.add(user)
        db.session.commit()
        flash('Account created! Please login.')
        return redirect(url_for('login'))

    return render_template('signup.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip()
        password = request.form['password']

        user = User.query.filter_by(email=email).first()
        if not user or not check_password_hash(user.password_hash, password):
            flash('Invalid email or password.')
            return redirect(url_for('login'))

        # Browser close/open ke baad bhi login rahe
        login_user(user, remember=True)
        return redirect(url_for('dashboard'))

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))


@app.route('/dashboard')
@login_required
def dashboard():
    my_adds = AddRequest.query.filter_by(
        user_id=current_user.id
    ).order_by(AddRequest.created_at.desc()).all()

    my_withdraws = WithdrawRequest.query.filter_by(
        user_id=current_user.id
    ).order_by(WithdrawRequest.created_at.desc()).all()

    return render_template(
        'dashboard.html',
        my_adds=my_adds,
        my_withdraws=my_withdraws
    )


@app.route('/tournaments')
@login_required
def tournaments():
    all_t = Tournament.query.order_by(Tournament.created_at.desc()).all()
    joins = TournamentJoin.query.filter_by(user_id=current_user.id).all()
    joined_ids = {j.tournament_id for j in joins}
    return render_template('tournaments.html', tournaments=all_t, joined_ids=joined_ids)


# detail + players list (sab users ke liye)
@app.route('/tournament/<int:t_id>')
@login_required
def tournament_detail(t_id):
    t = Tournament.query.get_or_404(t_id)
    joins = (
        TournamentJoin.query
        .filter_by(tournament_id=t_id)
        .order_by(TournamentJoin.slot.asc())
        .all()
    )
    return render_template('tournament_detail.html', tournament=t, joins=joins)


@app.route('/admin/create-tournament', methods=['GET', 'POST'])
@login_required
def create_tournament():
    if not current_user.is_admin:
        flash('Admin only.')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        name = request.form['name'].strip()
        game = request.form['game']
        mode = request.form['mode']
        entry_fee = float(request.form['entry_fee'])
        prize_pool = float(request.form['prize_pool'])
        max_slots = int(request.form['max_slots'])
        start_time_str = request.form['start_time']
        is_grand = bool(request.form.get('is_grand'))  # NEW

        start_time = datetime.fromisoformat(start_time_str) if start_time_str else None

        t = Tournament(
            name=name,
            game=game,
            mode=mode,
            entry_fee=entry_fee,
            prize_pool=prize_pool,
            max_slots=max_slots,
            start_time=start_time,
            is_grand=is_grand
        )
        db.session.add(t)
        db.session.commit()
        flash('Tournament created.')
        return redirect(url_for('tournaments'))

    return render_template('create_tournament.html')


# admin edit page
@app.route('/admin/tournament/<int:t_id>/edit', methods=['GET', 'POST'])
@login_required
def admin_edit_tournament(t_id):
    if not current_user.is_admin:
        flash('Admin only.')
        return redirect(url_for('tournaments'))

    t = Tournament.query.get_or_404(t_id)

    if request.method == 'POST':
        t.winner_note = request.form.get('winner_note', '').strip() or None
        t.room_id = request.form.get('room_id', '').strip() or None
        t.room_pass = request.form.get('room_pass', '').strip() or None
        t.admin_note = request.form.get('admin_note', '').strip() or None
        t.is_grand = bool(request.form.get('is_grand'))  # NEW

        new_status = request.form.get('status')
        if new_status in ['upcoming', 'live', 'finished']:
            t.status = new_status

        db.session.commit()
        flash('Tournament info updated.')
        return redirect(url_for('tournaments'))

    return render_template('admin_edit_tournament.html', t=t)


@app.route('/tournaments/<int:t_id>/join', methods=['GET', 'POST'])
@login_required
def join_tournament(t_id):
    t = Tournament.query.get_or_404(t_id)

    # tournament full ya closed
    if t.filled_slots >= t.max_slots or t.status not in ['upcoming', 'live']:
        flash('Tournament full ya closed hai.')
        return redirect(url_for('tournaments'))

    # agar already joined hai
    existing = TournamentJoin.query.filter_by(
        tournament_id=t_id, user_id=current_user.id
    ).first()
    if existing:
        flash('Aap pehle hi is tournament me joined ho.')
        return redirect(url_for('tournaments'))

    if request.method == 'POST':
        in_game_name = request.form['in_game_name'].strip()
        in_game_uid = request.form['in_game_uid'].strip()
        slot = int(request.form['slot'])

        # slot range check
        if slot < 1 or slot > t.max_slots:
            flash('Invalid slot number.')
            return redirect(url_for('join_tournament', t_id=t_id))

        # slot already taken?
        taken = TournamentJoin.query.filter_by(
            tournament_id=t_id, slot=slot
        ).first()
        if taken:
            flash('Ye slot already taken hai.')
            return redirect(url_for('join_tournament', t_id=t_id))

        # wallet selection
        wallet = request.form.get('wallet')
        fee = t.entry_fee

        if wallet not in ['winning', 'added']:
            flash('Please wallet select karo.')
            return redirect(url_for('join_tournament', t_id=t_id))

        if wallet == 'winning':
            if current_user.winning_balance < fee:
                flash('Winning wallet me itna balance nahi hai.')
                return redirect(url_for('join_tournament', t_id=t_id))
            current_user.winning_balance -= fee
        else:
            if current_user.added_balance < fee:
                flash('Added wallet me itna balance nahi hai.')
                return redirect(url_for('join_tournament', t_id=t_id))
            current_user.added_balance -= fee

        join = TournamentJoin(
            tournament_id=t_id,
            user_id=current_user.id,
            in_game_name=in_game_name,
            in_game_uid=in_game_uid,
            slot=slot
        )
        t.filled_slots += 1

        db.session.add(join)
        db.session.commit()
        flash('Tournament join ho gaya. Best of luck!')
        return redirect(url_for('tournaments'))

    # GET request – form show karo
    taken_slots = [
        j.slot for j in TournamentJoin.query.filter_by(tournament_id=t_id).all()
    ]
    return render_template(
        'join_tournament.html', tournament=t, taken_slots=taken_slots
    )


@app.route('/add-money', methods=['POST'])
@login_required
def add_money():
    amount = float(request.form['amount'])
    upi_id = request.form['upi_id'].strip()
    txn_id = request.form['txn_id'].strip()

    req = AddRequest(
        user_id=current_user.id,
        amount=amount,
        upi_id=upi_id,
        txn_id=txn_id
    )
    db.session.add(req)
    db.session.commit()
    flash('Add-money request submitted. Pehle UPI se payment karo, phir admin approve karega.')
    return redirect(url_for('dashboard'))


@app.route('/withdraw', methods=['POST'])
@login_required
def withdraw():
    amount = float(request.form['amount'])
    upi_id = request.form['upi_id'].strip()

    if amount <= 0 or amount > current_user.winning_balance:
        flash('Winning balance se zyada withdraw nahi kar sakte.')
        return redirect(url_for('dashboard'))

    req = WithdrawRequest(
        user_id=current_user.id,
        amount=amount,
        upi_id=upi_id
    )
    db.session.add(req)
    db.session.commit()
    flash('Withdraw request submitted. Admin approve karega.')
    return redirect(url_for('dashboard'))


# ------------- ADMIN SIMPLE APPROVAL -------------
@app.route('/admin')
@login_required
def admin_panel():
    if not current_user.is_admin:
        flash('Admin only.')
        return redirect(url_for('dashboard'))

    add_reqs = AddRequest.query.order_by(AddRequest.created_at.desc()).all()
    withdraw_reqs = WithdrawRequest.query.order_by(WithdrawRequest.created_at.desc()).all()
    return render_template(
        'admin.html',
        add_reqs=add_reqs,
        withdraw_reqs=withdraw_reqs
    )


@app.route('/admin/approve-add/<int:req_id>')
@login_required
def approve_add(req_id):
    if not current_user.is_admin:
        flash('Admin only.')
        return redirect(url_for('dashboard'))

    req = AddRequest.query.get_or_404(req_id)
    if req.status != 'approved':
        req.status = 'approved'
        user = User.query.get(req.user_id)
        user.added_balance += req.amount
        db.session.commit()
    return redirect(url_for('admin_panel'))


@app.route('/admin/approve-withdraw/<int:req_id>')
@login_required
def approve_withdraw(req_id):
    if not current_user.is_admin:
        flash('Admin only.')
        return redirect(url_for('dashboard'))

    req = WithdrawRequest.query.get_or_404(req_id)
    user = User.query.get(req.user_id)
    if req.status != 'paid' and user.winning_balance >= req.amount:
        req.status = 'paid'
        user.winning_balance -= req.amount
        db.session.commit()
    return redirect(url_for('admin_panel'))


@app.route('/admin/tournament/<int:t_id>/delete')
@login_required
def delete_tournament(t_id):
    if not current_user.is_admin:
        flash('Admin only.')
        return redirect(url_for('tournaments'))

    t = Tournament.query.get_or_404(t_id)
    TournamentJoin.query.filter_by(tournament_id=t_id).delete()
    db.session.delete(t)
    db.session.commit()
    flash('Tournament deleted.')
    return redirect(url_for('tournaments'))


@app.route('/admin/tournament/<int:t_id>/give-prize', methods=['POST'])
@login_required
def give_prize(t_id):
    if not current_user.is_admin:
        flash('Admin only.')
        return redirect(url_for('tournaments'))

    user_id = int(request.form['user_id'])
    amount = float(request.form['amount'])

    user = User.query.get_or_404(user_id)
    user.winning_balance += amount
    db.session.commit()
    flash(f'₹{amount} prize user {user.email} ko add ho gaya.')
    return redirect(url_for('tournaments'))


@app.route('/admin/tournament/<int:t_id>/set-winner', methods=['POST'])
@login_required
def set_winner(t_id):
    if not current_user.is_admin:
        flash('Admin only.')
        return redirect(url_for('tournaments'))

    user_id = int(request.form['user_id'])
    prize = float(request.form['prize'])

    user = User.query.get_or_404(user_id)
    user.winning_balance += prize

    t = Tournament.query.get_or_404(t_id)
    t.status = 'finished'

    db.session.commit()
    flash('Winner set ho gaya, prize add ho gaya.')
    return redirect(url_for('tournaments'))


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(is_admin=True).first():
            admin = User(
                email='pk1921338@gmail.com',
                password_hash=generate_password_hash('priyanshu'),
                is_admin=True
            )
            db.session.add(admin)
            db.session.commit()
    app.run(debug=True)
