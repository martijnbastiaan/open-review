from django.db import models
from openreview.apps.main.models.review import Vote
from openreview.apps.main.models.author import Author

__all__ = ["Keyword", "Paper"]


class Keyword(models.Model):
    label = models.TextField()

    def __str__(self):
        return self.label

    class Meta:
        app_label = "main"


class Paper(models.Model):
    doc_id = models.TextField(help_text="Identifier: can either be a real DOI or a domain-specific one. "
                                        "For example: arXiv:1403.0438.", null=True)
    title = models.TextField()
    abstract = models.TextField()
    publisher = models.TextField(null=True, blank=True)
    publish_date = models.DateField(null=True)
    urls = models.TextField(null=True, blank=True)

    # These fields are *probably* a bad idea performance wise.
    authors = models.ManyToManyField(Author)
    keywords = models.ManyToManyField(Keyword)

    def get_reviews(self):
        return self.reviews.filter(parent__isnull=True)
    
    def num_reviews(self):
        return len(self.get_reviews())

    def get_comments(self):
        return self.reviews.filter(parent__isnull=False)

    def get_votes(self, include_comments):
        """
        Returns votes, which gives a rough indicator of its popularity.

        @param include_comments: include reviews with parent != None.
        @type include_comments: bool

        @rtype: QuerySet(Review)
        """
        votes = Vote.objects.filter(review__paper=self)
        return votes if include_comments else votes.filter(parent=None)

    def __str__(self):
        return self.title

    class Meta:
        app_label = "main"