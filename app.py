import os

from flask import Flask, render_template, request, jsonify, flash, redirect, session, g 
from flask_debugtoolbar import DebugToolbarExtension
from sqlalchemy.exc import IntegrityError
from models import db, connect_db, Nugget, Keyword, Fakeout, Question, Quiz, Deck, JoinDeckQuestion, JoinDeckQuiz, JoinDeckNugget, User
from forms import UserAddForm, LoginForm, CreateDeckForm, CreateNuggetForm, AddUserCollaborator
from cohyponym import find_strong_cohyponyms, do_requests
from quizmaker import make_quiz

CURR_USER_KEY = "curr_user"

app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI']=(os.environ.get('DATABASE_URL','postgres:///monoblaine'))

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ECHO'] = False
app.config['DEBUG_TB_INTERCEPT_REDIRECTS'] = True
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', "it's a secret")
toolbar = DebugToolbarExtension(app)

connect_db(app)
#import seed

@app.before_request
def add_user_to_g():
    """If the visitor is logged in, add curr user to Flask global."""
    if CURR_USER_KEY in session:
        g.user = User.query.get(session[CURR_USER_KEY])
    else:
        g.user = None

def do_login(user):
    """Log in the user."""
    session[CURR_USER_KEY] = user.id

def do_logout():
    """Logout user."""
    if CURR_USER_KEY in session:
        del session[CURR_USER_KEY]

@app.route("/",methods=["GET","POST"])
def entrypage():
    """Show homepage:
    -anon users: no collections
    -logged in: owned collections, and nuggets
    """
    if g.user:
        my_decks = g.user.decks
        my_nuggets = g.user.nuggets
        return render_template('home.html')
        pass
    else:
        form = LoginForm()
        if form.validate_on_submit():
            user = User.authenticate(form.username.data.lower(),form.password.data)
            if user:
                do_login(user)
                flash(f"Hello, {user.username}!","success")
                return redirect("/")
            flash("Invalid credentials.","danger")
    return render_template('home-anon.html',form=form)

@app.route("/user/guest",methods=["GET"])
def make_me_guest():
    """Sign the user in as the guest/test account
    """
    if g.user:
        return redirect('/')
    else:
        user = User.authenticate('guest','guestPassword123')
        if user:
            do_login(user)
            flash(f"You are signed into the guest account. Please be try to avoid deleting data you didn't create","warning")
            return redirect("/")
        flash("Invalid credentials.","danger")
    return redirect('/')

@app.route('/user/signup',methods=["GET","POST"])
def signup():
    """Handle new user signup.
    Create a new user and add to DB. Redirect to homepage.
    If form not valid, present form.
    If there already is a user with that username: flash message and re-present form.
    """
    form = UserAddForm()
    if form.validate_on_submit():
        try:
            user = User.signup(
                username= form.username.data.lower(),
                password= form.password.data,
                email= form.email.data
            )
            db.session.commit()
        except IntegrityError:
            flash("Username already taken",'danger')
            return render_template('users/signup.html',form=form)
        
        do_login(user)
        return redirect('/')
    else:
        return render_template('signup.html',form=form)

@app.route('/logout')
def logout():
    """Handle logout of user."""
    do_logout()
    flash("You have been successfully logged out","warning")
    return redirect('/')

@app.route('/decks/<int:deck_id>/nuggets/create',methods=["GET","POST"])
def seenuggetscreenforspecificdeck(deck_id):
    if not g.user:
        flash("You need to create an account to make new nuggets.","danger")
        return redirect("/")
    form = CreateNuggetForm()
    decks = [Deck.query.get(deck_id)]
    if request.method=="POST":
        csrf_token = request.json.get("submission",None).get("csrf_token",None)
        f = {"csrf_token":csrf_token}
        request.form = f
        form.csrf_token.data = csrf_token
    if form.validate_on_submit():
        submitted_info = request.json.get("submission",None)
        nugget = Nugget(truth = submitted_info.get("Nugget"), user_id = g.user.id)
        db.session.add(nugget)
        db.session.commit()
        for input_keyword in submitted_info.get("Keywords"):
            keyword = Keyword.create_with_fakeouts(input_keyword,nugget.id)
        #seems like an unnecessary db commit
        db.session.commit()
        for deck_id in submitted_info.get("Decks",None):
            deck = Deck.query.get(deck_id)
            deck.my_nuggets.append(nugget)
            db.session.commit()
        flash("You have created a new nugget")
        return redirect("/")
    return render_template('/nuggetviewcontrol.html',form=form,nugget=None, decks = decks)


@app.route('/nuggets/create',methods=["GET","POST"])
def seeblanknuggetscreen():
    if not g.user:
        flash("You need to create an account to make new nuggets.","danger")
        return redirect("/")
    form = CreateNuggetForm()
    if request.method=="POST":
        csrf_token = request.json.get("submission",None).get("csrf_token",None)
        f = {"csrf_token":csrf_token}
        request.form = f
        form.csrf_token.data = csrf_token
    if form.validate_on_submit():
        submitted_info = request.json.get("submission",None)
        nugget = Nugget(truth = submitted_info.get("truth"), user_id = g.user.id)
        db.session.add(nugget)
        db.session.commit()
        for input_keyword in submitted_info.get("keywords"):
            keyword = Keyword.create_with_fakeouts(input_keyword,nugget.id)
        #seems like an unnecessary db commit
        db.session.commit()
        for deck_id in submitted_info.get("Decks",None):
            deck = Deck.query.get(deck_id)
            deck.my_nuggets.append(nugget)
            db.session.commit()
        flash("You have created a new nugget")
        return redirect("/")
    return render_template('/nuggetviewcontrol.html',form=form,nugget=None, decks = None,nugget_dict = {})
    #return render_template('nuggetenter.html',form=form)

@app.route('/nuggets/view/<int:nugget_id>',methods=["GET","POST"])
def seepopulatednuggetscreen(nugget_id):
    if not g.user:
        flash("Access unauthorized.","danger")
        return redirect("/")
    nugget = Nugget.query.get(nugget_id)
    form = CreateNuggetForm()
    if request.method=="POST":
        csrf_token = request.json.get("submission",None).get("csrf_token",None)
        f = {"csrf_token":csrf_token}
        request.form = f
        form.csrf_token.data = csrf_token
    if form.validate_on_submit():               
        submitted_info = request.json.get("submission",None)
        nugget.update(submitted_info)

        flash("You have updated a nugget")
        return redirect("/")
    
    return render_template('/nuggetviewcontrol.html',nugget=nugget,form=form, decks = nugget.my_decks,nugget_dict = nugget.to_dict())

@app.route('/decks/create',methods=["GET","POST"])
def create_deck():
    """Handle a new deck creation
    Create a new deck and add to DB. Redirect to homepage.
    If form is not valid, present form.
    """
    if not g.user:
        flash("Access unauthorized.","danger")
        return redirect("/")
    form = CreateDeckForm()

    if form.validate_on_submit():
        deck = Deck(name=form.deckname.data,
            description=form.description.data,
            visibility = form.visibility.data)
        g.user.decks.append(deck)
        db.session.commit()
        return redirect("/")
    return render_template('/createdeck.html',form=form)

@app.route('/decks/view/<int:deck_id>',methods=["POST","GET"])
def view_deck(deck_id):
    deck = Deck.query.get(deck_id)
    if not g.user:
        flash("Access unauthorized.","danger")
        return redirect("/")
    formadduser = AddUserCollaborator()
    access_control = "VISITOR"
    if deck in g.user.decks:
        access_control = "ADMIN"
    if g.user in deck.my_users:
        access_control = "COLLABORATOR"
    if formadduser.validate_on_submit():
        collab_user = User.query.filter_by(username=formadduser.collaborator_username.data.lower()).first()
        if collab_user == None:
            flash("The user you have tried to add does not exist","danger")
            return redirect(f"/decks/view/{deck_id}")
        deck.my_users.append(collab_user)
        db.session.commit()

    return render_template('showdeck.html',user = g.user, deck=deck,form=formadduser, access_control = access_control)

@app.route('/decks/quiz/<int:deck_id>')
def run_quiz(deck_id):
    if not g.user:
        flash("Access unauthorized.","danger")
        return redirect("/")
    deck = Deck.query.get(deck_id)
    quiz = make_quiz(deck)
    return render_template('viewquiz.html',quiz=quiz,deck_id=deck_id)



@app.route('/decks/<int:deck_id>/delete',methods=["POST"])
def delete_deck(deck_id):
    """Delete a deck."""
    if not g.user:
        flash("Access unauthorized.","danger")
        return redirect("/")
    deck = Deck.query.get(deck_id)
    if deck.user_id != g.user.id:
        flash("Access unauthorized.","danger")
        return redirect("/")
    db.session.delete(deck)
    db.session.commit()
    return redirect(f'/')

@app.route('/decks/<int:deck_id>/collab_user/<int:user_id>/remove',methods=["POST"])
def remove_collab_user(deck_id,user_id):
    """Disconnect a user from a deck"""
    if not g.user:
        flash("Access unauthorized.","danger")
        return redirect("/")
    deck = Deck.query.get(deck_id)
    if deck.user_id != g.user.id:
        flash("This is not a deck that you own. You cannot make this change","danger")
    user = User.query.get(user_id)
    if user not in deck.my_users:
        flash("This user is not currently collaborating with this deck","danger")    
    elif user in deck.my_users:
        deck.my_users.remove(user)
        db.session.commit()
        flash(f'{user.username} has been successfully removed from deck collaboration')
    return redirect(f'decks/view/{deck_id}')
    

@app.route('/nuggets/<int:nugget_id>/delete',methods=["POST"])
def delete_nugget(nugget_id):
    """Delete a nugget."""

    if not g.user:
        flash("Access unauthorized.","danger")
        return redirect("/")
    nugget = Nugget.query.get(nugget_id)
    if nugget.user_id != g.user.id:
        flash("Access unauthorized.","danger")
        return redirect("/")
    db.session.delete(nugget)
    db.session.commit()
    return redirect(f'/')

@app.route("/api/get_my_decks",methods=["GET"])
def get_decks():
    collab_decks = g.user.my_decks + g.user.decks
    decks = [{"id":deck.id,"name":deck.name} for deck in collab_decks]
    return jsonify(decks=decks)

@app.route("/api/get_users/usernames",methods=["GET"])
def get_usernames():
    users = User.query.all()
    usernames = [user.username for user in users]
    return jsonify(usernames=usernames)

@app.route("/get_fakeout",methods=["POST"])
def get_fakeout_words():
    #import pdb; pdb.set_trace()
    words = request.json.get("words",None)
    hypernym_collection = do_requests(words)
    return jsonify(fakeoutResults=hypernym_collection)

