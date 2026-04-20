import graphene
import apps.movies.schema
import apps.accounts.schema

class Query(apps.movies.schema.Query, apps.accounts.schema.Query, graphene.ObjectType):
    pass

class Mutation(apps.movies.schema.Mutation, apps.accounts.schema.Mutation, graphene.ObjectType):
    pass

schema = graphene.Schema(query=Query, mutation=Mutation)
