#!/usr/bin/env bash
set -e

function step() {
    pos=$(caller)
    echo $pos $@
}

wyag=$(realpath ./wyag)

testdir=/tmp/wyag-tests
if [[ -e $testdir ]]; then
    rm -rf $testdir/*
else
    mkdir $testdir
fi
cd $testdir
step "working on $(pwd)"

step Create repos
"$wyag" init left
git init right > /dev/null

# Repeatable test entry point for repo_create
test_repo_create_entrypoint() {
    local tmp_repo_test
    tmp_repo_test=$(mktemp -d /tmp/wyag-repocreate-XXXXXX)

    # 1. Successful repository creation and state verification
    local target="$tmp_repo_test/fresh_repo"
    "$wyag" init "$target" > /dev/null

    if [[ ! -d "$target/.git/objects" ]]; then
        echo "Missing .git/objects"
        rm -rf "$tmp_repo_test"
        return 1
    fi
    if [[ ! -d "$target/.git/refs/heads" ]]; then
        echo "Missing .git/refs/heads"
        rm -rf "$tmp_repo_test"
        return 1
    fi
    if [[ ! -d "$target/.git/refs/tags" ]]; then
        echo "Missing .git/refs/tags"
        rm -rf "$tmp_repo_test"
        return 1
    fi
    if [[ ! -f "$target/.git/HEAD" ]]; then
        echo "Missing .git/HEAD"
        rm -rf "$tmp_repo_test"
        return 1
    fi
    if [[ ! -f "$target/.git/config" ]]; then
        echo "Missing .git/config"
        rm -rf "$tmp_repo_test"
        return 1
    fi
    if ! grep -q "ref: refs/heads/master" "$target/.git/HEAD"; then
        echo "Incorrect HEAD reference"
        rm -rf "$tmp_repo_test"
        return 1
    fi

    # 2. Failure propagation: path is an existing regular file
    local file_target="$tmp_repo_test/file_target"
    touch "$file_target"
    set +e
    "$wyag" init "$file_target" > /dev/null 2>&1
    local fail_file_code=$?
    set -e
    if [[ $fail_file_code -eq 0 ]]; then
        echo "Expected failure when target is a file, but succeeded"
        rm -rf "$tmp_repo_test"
        return 1
    fi

    # 3. Failure propagation: .git already exists and is not empty
    touch "$target/.git/blocking_file"
    set +e
    "$wyag" init "$target" > /dev/null 2>&1
    local fail_nonempty_code=$?
    set -e
    if [[ $fail_nonempty_code -eq 0 ]]; then
        echo "Expected failure when .git is not empty, but succeeded"
        rm -rf "$tmp_repo_test"
        return 1
    fi

    # 4. Direct Python contract verification
    local wyag_dir
    wyag_dir=$(dirname "$wyag")
    python3 -c "
import os, sys
sys.path.insert(0, '$wyag_dir')
import libwyag

# Clean creation
r = libwyag.repo_create('$tmp_repo_test/py_repo')
assert r is not None
assert os.path.isdir(os.path.join(r.gitdir, 'objects'))

# Failure propagation on existing file
try:
    libwyag.repo_create('$file_target')
    assert False, 'Expected exception'
except Exception as e:
    assert 'not a directory' in str(e).lower()
"

    # Clean up temporary state
    rm -rf "$tmp_repo_test"
    return 0
}

step "repo_create repeatable entrypoint"
test_repo_create_entrypoint

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




step THIS WAS A TRIUMPH
step "I'M MAKING A NOTE HERE"
step "HUGE SUCCESS"
