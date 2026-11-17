#!/usr/bin/env bash
set -e

function step() {
    pos=$(caller)
    echo $pos $@
}

wyag=$(realpath ./wyag)

testdir=$(mktemp -d "${TMPDIR:-/tmp}/wyag-tests.XXXXXX")
trap 'rm -rf "$testdir"' EXIT
cd $testdir
step "working on $(pwd)"

step Create repos
"$wyag" init left
git init right > /dev/null

step status
cd left
git status > /dev/null
cd ../right
git status > /dev/null
cd ..

step hash-object
echo "Don't read me" > README
"$wyag" hash-object README > hash1
git hash-object README > hash2
cmp --quiet hash1 hash2

step hash-object -w
cd left
"$wyag" hash-object -w ../README > /dev/null
cd ../right
git hash-object -w ../README > /dev/null
cd ..
ls left/.git/objects/b1/7df541639ec7814a9ad274e177d9f8da1eb951 > /dev/null
ls right/.git/objects/b1/7df541639ec7814a9ad274e177d9f8da1eb951 > /dev/null

step cat-file
cd left
"$wyag" cat-file blob b17d > ../file1
cd ../right
git cat-file blob b17d > ../file2
cd ..
cmp file1 file2

step cat-file with long hash
cd left
"$wyag" cat-file blob b17df541639ec7814a9ad274e177d9f8da1eb951 > ../file1
cd ../right
git cat-file blob b17df541639ec7814a9ad274e177d9f8da1eb951 > ../file2
cd ..
cmp file1 file2

step "Create commit (git only, nothing is tested)" #@FIXME Add wyag commit
cd left
echo "Aleph" > hebraic-letter.txt
git add hebraic-letter.txt
GIT_AUTHOR_DATE="2010-01-01 01:02:03 +0100" \
               GIT_AUTHOR_NAME="wyag-tests.sh" \
               GIT_AUTHOR_EMAIL="wyag@example.com" \
               GIT_COMMITTER_DATE="2010-01-01 01:02:03 +0100" \
               GIT_COMMITTER_NAME="wyag-tests.sh" \
               GIT_COMMITTER_EMAIL="wyag@example.com" \
               git commit --no-gpg-sign -m "Initial commit" > /dev/null
cd ../right
echo "Aleph" > hebraic-letter.txt
git add hebraic-letter.txt
GIT_AUTHOR_DATE="2010-01-01 01:02:03 +0100" \
               GIT_AUTHOR_NAME="wyag-tests.sh" \
               GIT_AUTHOR_EMAIL="wyag@example.com" \
               GIT_COMMITTER_DATE="2010-01-01 01:02:03 +0100" \
               GIT_COMMITTER_NAME="wyag-tests.sh" \
               GIT_COMMITTER_EMAIL="wyag@example.com" \
               git commit --no-gpg-sign -m "Initial commit" > /dev/null

cd ..

step cat-file on commit object without indirection
cd left
"$wyag" cat-file commit HEAD > ../file1
cd ../right
git cat-file commit HEAD > ../file2
cd ..
cmp file1 file2

step cat-file on tree object redirected from commit
cd left
"$wyag" cat-file tree HEAD > ../file1
cd ../right
git cat-file tree HEAD > ../file2
cd ..
cmp file1 file2

step "Add some directories and commits (git only, nothing is tested)" #@FIXME Add wyag commit
cd left
mkdir a
echo "Alpha" > a/greek_letters
mkdir b
echo "Hamza" > a/arabic_letters
git add a/*
GIT_AUTHOR_DATE="2010-01-01 01:02:03 +0100" \
               GIT_AUTHOR_NAME="wyag-tests.sh" \
               GIT_AUTHOR_EMAIL="wyag@example.com" \
               GIT_COMMITTER_DATE="2010-01-01 01:02:03 +0100" \
               GIT_COMMITTER_NAME="wyag-tests.sh" \
               GIT_COMMITTER_EMAIL="wyag@example.com" \
               git commit --no-gpg-sign -m "Commit 2" > /dev/null
cd ../right
mkdir a
echo "Alpha" > a/greek_letters
mkdir b
echo "Hamza" > a/arabic_letters
git add a/*
GIT_AUTHOR_DATE="2010-01-01 01:02:03 +0100" \
               GIT_AUTHOR_NAME="wyag-tests.sh" \
               GIT_AUTHOR_EMAIL="wyag@example.com" \
               GIT_COMMITTER_DATE="2010-01-01 01:02:03 +0100" \
               GIT_COMMITTER_NAME="wyag-tests.sh" \
               GIT_COMMITTER_EMAIL="wyag@example.com" \
               git commit --no-gpg-sign -m "Commit 2" > /dev/null
cd ..

step ls-tree
cd left
"$wyag" ls-tree HEAD > ../file1
cd ../right
git ls-tree HEAD > ../file2
cd ..
cmp file1 file2

step checkout
# Git and Wyag syntax are different here
cd left
"$wyag" checkout HEAD ../temp1
mkdir ../temp2
cd  ../temp2
git --git-dir=../right/.git checkout .
cd ..
diff -r temp1 temp2
rm -rf temp1 temp2

step rev-parse
cd left
"$wyag" rev-parse HEAD  > ../file1
"$wyag" rev-parse 75ee4 >> ../file1
"$wyag" rev-parse 8a617  >> ../file1
#@FIXME Tags missing, branches missing, remotes missing
cd ../right
git rev-parse HEAD   > ../file2
git rev-parse 75ee4 >> ../file2
git rev-parse 8a617  >> ../file2
cd ..
cmp file1 file2

step "ls-files "
cd left
"$wyag" ls-files > ../file1
cd ../right
git ls-files > ../file2
cd ..
cmp file1 file2

gitignore_prepare() {
    mkdir -p a/b/c/
    echo "!*.txt" > a/b/c/.gitignore
    echo "*.txt" > a/b/.gitignore
    echo "*.org" > a/.gitignore
    git add -A
}

step "gitignore"
cd left
gitignore_prepare
"$wyag" check-ignore a/b/c/hello.txt > ../file1
"$wyag" check-ignore a/b/hello.txt >> ../file1
"$wyag" check-ignore a/hello.org >> ../file1
"$wyag" check-ignore hello.org >> ../file1
cd ../right
set +e # git will return with non-zero
gitignore_prepare
git check-ignore a/b/c/hello.txt > ../file2
git check-ignore a/b/hello.txt >> ../file2
git check-ignore a/hello.org >> ../file2
git check-ignore hello.org >> ../file2
set -e
cd ..
cmp file1 file2

step "add stages files and rejects empty and missing paths"
"$wyag" init add
printf 'alpha\n' > add/notes.txt
printf 'spaced\n' > "add/file with space.txt"
set +e
(cd add && "$wyag" add notes.txt "file with space.txt") > add-stdout 2> add-stderr
add_status=$?
set -e
test "$add_status" -eq 0
test ! -s add-stdout
test ! -s add-stderr
git -C add ls-files --stage > add-wyag-index
git init -q -b master add-reference
cp add/notes.txt add-reference/notes.txt
cp "add/file with space.txt" "add-reference/file with space.txt"
git -C add-reference add -- notes.txt "file with space.txt"
git -C add-reference ls-files --stage > add-git-index
diff -u add-git-index add-wyag-index
git -C add cat-file -e "$(git -C add ls-files --format='%(objectname)' -- notes.txt)"

"$wyag" init add-empty
set +e
(cd add-empty && "$wyag" add) > add-empty-stdout 2> add-empty-stderr
empty_add_status=$?
set -e
test "$empty_add_status" -eq 2
test ! -s add-empty-stdout
grep -q "required: path" add-empty-stderr
test ! -e add-empty/.git/index

set +e
(cd add-empty && "$wyag" add missing.txt) > add-missing-stdout 2> add-missing-stderr
missing_add_status=$?
set -e
test "$missing_add_status" -ne 0
test ! -s add-missing-stdout
grep -q "Not a file, or outside the worktree" add-missing-stderr
test ! -e add-empty/.git/index




step THIS WAS A TRIUMPH
step "I'M MAKING A NOTE HERE"
step "HUGE SUCCESS"
