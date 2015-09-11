import json


class Marks(object):
    def __init__(self, path):
        self.path = path
        self.refs = {}
        self.marks = {}
        self.rev_marks = {}
        self.last_mark = 0
        self.load()

    def load(self):
        try:
            with open(self.path) as fd:
                toc = json.load(fd)
        except IOError:
            return

        self.refs = toc['refs']
        self.marks = toc['marks']
        self.rev_marks = dict((v, k) for k, v in self.marks.items())

        if self.marks:
            self.last_mark = sorted(int(x[1:]) for x in self.marks.keys())[-1]

    def store(self):
        with open(self.path, 'w') as fd:
            json.dump(self.to_dict(), fd, indent=2)

    def to_dict(self):
        return {
            'refs': self.refs,
            'marks': self.marks,
            'last_mark': self.last_mark,
        }

    def next_mark(self):
        self.last_mark += 1
        return ':%d' % self.last_mark

    def from_rev(self, rev):
        return self.rev_marks[rev]

    def from_mark(self, mark):
        return self.marks[mark]

    def is_marked(self, rev):
        return rev in self.rev_marks

    def add_rev(self, rev):
        mark = self.next_mark()
        self.marks[mark] = rev
        self.rev_marks[rev] = mark
        return mark

    def add_mark(self, mark, rev):
        self.marks[mark] = rev
        self.rev_marks[rev] = mark
        self.last_mark = mark

    def get_ref(self, ref):
        return self.refs.get(ref)

    def set_ref(self, ref, hash):
        self.refs[ref] = hash
