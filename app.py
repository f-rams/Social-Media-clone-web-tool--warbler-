import os
from flask import Flask, render_template, request, flash, redirect, session, g
from flask_debugtoolbar import DebugToolbarExtension
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import NullPool

from forms import UserAddForm, LoginForm, MessageForm, EditForm
from models import db, connect_db, User, Message, Likes

CURR_USER_KEY = "curr_user"


DATABASE_URL = os.getenv('DATABASE_URL')
SECRET_KEY = os.getenv('SECRET_KEY')


app = Flask(__name__)


app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL


app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_pre_ping": True, "pool_recycle": 300, "poolclass": NullPool}
app.config['SQLALCHEMY_ECHO'] = False
app.config['DEBUG_TB_INTERCEPT_REDIRECTS'] = True
app.config['SECRET_KEY'] = SECRET_KEY
app.app_context().push()


connect_db(app)


##############################################################################
# User signup/login/logout


@app.before_request
def add_user_to_g():
    """If we're logged in, add curr user to Flask global."""

    if CURR_USER_KEY in session:
        g.user = User.query.get(session[CURR_USER_KEY])

    else:
        g.user = None


def do_login(user):
    """Log in user."""

    session[CURR_USER_KEY] = user.id


def do_logout():
    """Logout user."""

    if CURR_USER_KEY in session:
        del session[CURR_USER_KEY]


@app.route('/signup', methods=["GET", "POST"])
def signup():

    form = UserAddForm()

    if form.validate_on_submit():
        try:
            user = User.signup(
                username=form.username.data,
                password=form.password.data,
                email=form.email.data,
                image_url=form.image_url.data or User.image_url.default.arg,
            )
            db.session.commit()
            do_login(user)
            db.session.close()

            return redirect("/")

        except IntegrityError as e:
            db.session.rollback()
            # Print the error message for debugging
            print(f"IntegrityError: {e}")
            flash("Username/Email already taken", 'danger')
            return render_template('users/signup.html', form=form)
        except Exception as e:
            db.session.rollback()
            # Print any other unexpected errors for debugging
            print(f"Unexpected error: {e}")
            flash("An unexpected error occurred. Please try again.", 'danger')
            return render_template('users/signup.html', form=form)

    else:

        return render_template('users/signup.html', form=form)


@app.route('/login', methods=["GET", "POST"])
def login():
    """Handle user login."""

    form = LoginForm()

    if form.validate_on_submit():
        user = User.authenticate(form.username.data,
                                 form.password.data)

        if user:
            do_login(user)
            flash(f"Hello, {user.username}!", "success")
            db.session.close()
            return redirect("/")

        flash("Invalid credentials.", 'danger')

    return render_template('users/login.html', form=form)


@app.route('/logout')
def logout():

    do_logout()
    db.session.close()
    flash('Logout succeeded')
    return redirect('/login')


##############################################################################
# General user routes:

@app.route('/users')
def list_users():

    search = request.args.get('q')

    if not search:
        users = User.query.all()
    else:
        users = User.query.filter(User.username.like(f"%{search}%")).all()

    return render_template('users/index.html', users=users)


@app.route('/users/<int:user_id>')
def users_show(user_id):

    user = User.query.get_or_404(user_id)

    messages = (Message
                .query
                .filter(Message.user_id == user_id)
                .order_by(Message.timestamp.desc())
                .limit(100)
                .all())
    return render_template('users/show.html', user=user, messages=messages)


@app.route('/users/<int:user_id>/following')
def show_following(user_id):
    """Show list of people this user is following."""

    if not g.user:
        flash("Access unauthorized.", "danger")
        return redirect("/")

    user = User.query.get_or_404(user_id)
    return render_template('users/following.html', user=user)


@app.route('/users/<int:user_id>/followers')
def users_followers(user_id):
    """Show list of followers of this user."""

    if not g.user:
        flash("Access unauthorized.", "danger")
        return redirect("/")

    user = User.query.get_or_404(user_id)
    return render_template('users/followers.html', user=user)


@app.route('/users/follow/<int:follow_id>', methods=['POST'])
def add_follow(follow_id):
    """Add a follow for the currently-logged-in user."""

    if not g.user:
        flash("Access unauthorized.", "danger")
        return redirect("/")

    followed_user = User.query.get_or_404(follow_id)
    g.user.following.append(followed_user)
    db.session.commit()

    return redirect(f"/users/{g.user.id}/following")


@app.route('/users/stop-following/<int:follow_id>', methods=['POST'])
def stop_following(follow_id):
    """Have currently-logged-in-user stop following this user."""

    if not g.user:
        flash("Access unauthorized.", "danger")
        return redirect("/")

    followed_user = User.query.get(follow_id)
    g.user.following.remove(followed_user)
    db.session.commit()

    return redirect(f"/users/{g.user.id}/following")


@app.route('/users/profile/<int:id>', methods=["GET", "POST"])
def profile(id):
    """Update profile for current user."""
    form = EditForm()
    logged_user = User.query.get(id)
    if form.validate_on_submit():
        user = User.authenticate(logged_user.username,
                                 form.password.data)

        if user:
            if form.username.data == '':
                logged_user.username = logged_user.username
            else:
                logged_user.username = form.username.data
            if form.image_url.data == '':
                logged_user.image_url = logged_user.image_url
            else:
                logged_user.image_url = form.image_url.data
            if form.bio.data == '':
                logged_user.bio = logged_user.bio
            else:
                logged_user.bio = form.bio.data
            if form.email.data == '':
                logged_user.email = logged_user.email
            else:
                logged_user.email = form.email.data
            if form.header_image_url.data == '':
                logged_user.email = logged_user.header_image_url
            else:
                logged_user.header_image_url = form.header_image_url.data
            if form.location.data == '':
                logged_user.email = logged_user.location
            else:
                logged_user.location = form.location.data
            db.session.commit()
            flash("Edit successful", "success")
            return redirect(f"/users/{logged_user.id}")

    return render_template('/users/edit.html', form=form, user=logged_user)


@app.route('/users/delete', methods=["POST"])
def delete_user():
    """Delete user."""

    if not g.user:
        flash("Access unauthorized.", "danger")
        return redirect("/")

    do_logout()

    db.session.delete(g.user)
    db.session.commit()

    return redirect("/signup")


##############################################################################
# Messages routes:

@app.route('/messages/new', methods=["GET", "POST"])
def messages_add():
    """Add a message:

    Show form if GET. If valid, update message and redirect to user page.
    """

    if not g.user:
        flash("Access unauthorized.", "danger")
        return redirect("/")

    form = MessageForm()

    if form.validate_on_submit():
        msg = Message(text=form.text.data)
        g.user.messages.append(msg)
        db.session.commit()

        return redirect(f"/users/{g.user.id}")

    return render_template('messages/new.html', form=form)


@app.route('/messages/<int:message_id>', methods=["GET"])
def messages_show(message_id):
    """Show a message."""

    msg = Message.query.get(message_id)
    return render_template('messages/show.html', message=msg)


@app.route('/messages/<int:message_id>/delete', methods=["POST"])
def messages_destroy(message_id):
    """Delete a message."""

    if not g.user:
        flash("Access unauthorized.", "danger")
        return redirect("/")

    msg = Message.query.get(message_id)
    db.session.delete(msg)
    db.session.commit()

    return redirect(f"/users/{g.user.id}")


##############################################################################
# Homepage and error pages


@app.route('/')
def homepage():
    """Show homepage:

    - logged in: 100 most recent messages of followed_users
    """

    if g.user:
        following = [user.id for user in g.user.following]
        following.append(g.user.id)
        messages = (Message
                    .query.filter(Message.user_id.in_(following))
                    .order_by(Message.timestamp.desc())
                    .limit(100)
                    .all())
        likes = [like.message_id for like in Likes.query.all()]
        return render_template('home.html', messages=messages, likes=likes)

    else:
        return render_template('home-anon.html')


# Like message route


@app.route('/users/add_like/<int:msg_id>/<int:user_id>', methods=['POST'])
def add_like(msg_id, user_id):
    like = Likes.query.filter(Likes.message_id == msg_id).first()
    likes = [like.message_id for like in Likes.query.all()]
    if msg_id not in likes:
        like = Likes(user_id=user_id, message_id=msg_id)
        db.session.add(like)
        db.session.commit()
        return redirect('/')
    else:
        db.session.delete(like)
        db.session.commit()
        return redirect('/')


@app.route('/users/<int:user_id>/likes')
def user_likes(user_id):
    user = User.query.get(user_id)
    likes = [like.message_id for like in Likes.query.all()]
    return render_template('/users/likes.html', user=user, likes=likes)


@app.route('/users/<int:user_id>/<int:msg_id>', methods=['POST'])
def add_like2(user_id, msg_id):
    like = Likes.query.filter(Likes.message_id == msg_id).first()
    db.session.delete(like)
    db.session.commit()
    return redirect(f'/users/{user_id}/likes')
