import graphene
from graphene_django import DjangoObjectType
from .models import User
from django.contrib.auth import authenticate, login, logout

class UserType(DjangoObjectType):
    class Meta:
        model = User
        fields = ("id", "username", "email", "role", "is_active", "is_staff", "date_joined")

class Register(graphene.Mutation):
    class Arguments:
        username = graphene.String(required=True)
        password = graphene.String(required=True)
        email = graphene.String()

    user = graphene.Field(UserType)
    success = graphene.Boolean()

    def mutate(self, info, username, password, email=None):
        if User.objects.filter(username=username).exists():
            raise Exception("Username already exists")
        user = User.objects.create_user(username=username, password=password, email=email)
        return Register(user=user, success=True)

class Login(graphene.Mutation):
    class Arguments:
        username = graphene.String(required=True)
        password = graphene.String(required=True)

    user = graphene.Field(UserType)
    success = graphene.Boolean()

    def mutate(self, info, username, password):
        user = authenticate(username=username, password=password)
        if user is not None:
            if info.context:
                login(info.context, user)
            return Login(user=user, success=True)
        raise Exception("Invalid credentials")

class Logout(graphene.Mutation):
    success = graphene.Boolean()

    def mutate(self, info):
        if info.context:
            logout(info.context)
        return Logout(success=True)

class Mutation(graphene.ObjectType):
    register = Register.Field()
    login = Login.Field()
    logout = Logout.Field()

class Query(graphene.ObjectType):
    me = graphene.Field(UserType)
    users = graphene.List(UserType)

    def resolve_me(self, info):
        user = info.context.user
        if user.is_anonymous:
            return None
        return user

    def resolve_users(self, info):
        # Authorization check
        user = info.context.user
        if not user.is_authenticated or user.role != "ADMIN":
            raise Exception("Unauthorized: Admin access required")
        return User.objects.all()
