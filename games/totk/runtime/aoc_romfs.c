/* Breath of the Wild add-on content (botw.md): the DLC's RomFS images, read-only volumes beside the game's (romfs.c), listed
   by nn::aoc and mounted as the game asks (nn::fs::MountAddOnContent("aoc", 1, ...)). The game lists two add-on contents
   (index 1: the expansion pass packs, 7,094 files; index 2: one file) and mounts index 1 only. Each volume is the image
   games/botw/scripts/extract_aoc_romfs.py extracted and indexed, verified against aoc-config.txt in the game data folder
   (game_data.h, scripts/prepare_romfs_backend.py --aoc: SHA-256 of the image
   once, then a proof record as romfs.c keeps one; the index on every start). Built into the Breath of the Wild runtime
   only; fs_host.c and services.c reach it through the GAME_BOTW macros of fs_host.h. */
#ifdef GAME_BOTW
#include "runtime.h"
#include "game_data.h"
#include "game_version.h"
#include "fs_host.h"
#include "romfs_path.h"
#include "totk_ui_lang.h"
#include <CommonCrypto/CommonDigest.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#define NOT_FOUND 0x202u
#define UNSUPPORTED 0x6402u
#define INVALID 0xe402u
#define AOC_MAX 2
#define AOC_NH 1024
#define AOC_HANDLE_BASE 0x400000000ULL   /* its own range: fs_host.c uses 0x200000000 (files) and 0x300000000 (directories), romfs.c 0x100000000 */
typedef struct { uint64_t offset, size; uint32_t name, len; } Entry;
typedef struct { char *name, *path; uint64_t size; struct stat identity; } DlcMod;
typedef struct {
    int index; uint64_t image_size; const char *image_sha, *index_sha;
    uint8_t *index_bytes; size_t index_size; uint64_t file_count, strings_offset; int image_fd; char mount[32]; int loaded; DlcMod *mods; size_t nmods;
} Vol;
static Vol vols[AOC_MAX] = {   /* sizes and hashes: config_load */
    {1, 0, NULL, NULL, NULL, 0, 0, 0, -1, "", 0, NULL, 0},
    {2, 0, NULL, NULL, NULL, 0, 0, 0, -1, "", 0, NULL, 0},
};
static struct { uint8_t vol; uint64_t entry; uint32_t mod; int fd; } handles[AOC_NH];   /* entry = file index + 1; 0 is free */
static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
static void need(int c, const char *m) { if (!c) runtime_fail(m); }
static pthread_once_t config_once = PTHREAD_ONCE_INIT;
static unsigned present_mask;   /* bit index - 1: the volume was extracted and indexed */
static void config_load(void) {
    present_mask = (unsigned)runtime_game_number("aoc-config.txt", "AOC_PRESENT_MASK");
    for (int i = 0; i < AOC_MAX; i++) {
        if (!((present_mask >> i) & 1)) continue;
        char key[32]; Vol *v = &vols[i];
        snprintf(key, sizeof key, "AOC%d_IMAGE_SIZE", v->index); v->image_size = runtime_game_number("aoc-config.txt", key);
        snprintf(key, sizeof key, "AOC%d_IMAGE_SHA256", v->index); v->image_sha = runtime_game_sha256("aoc-config.txt", key);
        snprintf(key, sizeof key, "AOC%d_INDEX_SHA256", v->index); v->index_sha = runtime_game_sha256("aoc-config.txt", key);
    }
}
static int present(const Vol *v) { pthread_once(&config_once, config_load); return (present_mask >> (v->index - 1)) & 1; }
static void vol_dir(const Vol *v, char *out, size_t cap) {
    const char *dir = getenv("TOTK_AOC");   /* the folder holding <index>/; default beside the game's RomFS */
    need(snprintf(out, cap, "%s/%d", dir && *dir ? dir : "extracted/" TOTK_GAME_DIR "/aoc", v->index) < (int)cap, "add-on content path");
}
static Entry entry(const Vol *v, uint64_t i) { Entry e; memcpy(&e, v->index_bytes + 24 + i * 24, 24); return e; }
static const char *entry_name(const Vol *v, Entry e) { return (const char *)v->index_bytes + v->strings_offset + e.name; }
static void sha_fd(int fd, const char *expected, uint64_t total, const char *what) {
    CC_SHA256_CTX c; CC_SHA256_Init(&c); uint8_t *buf = malloc(8 << 20); need(buf != NULL, "hash buffer"); uint64_t done = 0;
    for (;;) { ssize_t n = pread(fd, buf, 8 << 20, (off_t)done); if (n < 0) runtime_fail("add-on content read"); if (!n) break; CC_SHA256_Update(&c, buf, (CC_LONG)n); done += (uint64_t)n;
        if (total) runtime_boot_progress(what, done, total); }
    free(buf);
    uint8_t d[32]; CC_SHA256_Final(d, &c); char hex[65]; for (int i = 0; i < 32; i++) snprintf(hex + 2 * i, 3, "%02x", d[i]);
    if (total && done != total) runtime_fail("add-on content image size changed while hashing");
    if (strcmp(hex, expected)) { fprintf(stderr, "[botw] add-on content %s: SHA-256 %s, expected %s\n", what, hex, expected); runtime_fail("add-on content image does not match the extraction record"); }
}
/* DLC mods are a separate overlay tree: TOTK_AOC_MODS/<index>/manifest.tsv, or
   <TOTK_ROMFS_MODS>-aoc/<index>/manifest.tsv. Base and DLC files never share a namespace. */
static uint64_t lower(const Vol *v, const char *name);
static void hash_range(int fd, uint64_t offset, uint64_t size, const char *expected) {
    CC_SHA256_CTX c; CC_SHA256_Init(&c); uint8_t buf[65536]; uint64_t done=0;
    while(done<size) { size_t n=size-done>sizeof buf?sizeof buf:(size_t)(size-done);
        ssize_t got=pread(fd,buf,n,(off_t)(offset+done)); need(got>0,"DLC mod hash read");
        CC_SHA256_Update(&c,buf,(CC_LONG)got);done+=(uint64_t)got; }
    uint8_t digest[32];char hex[65];CC_SHA256_Final(digest,&c);
    for(int i=0;i<32;i++)snprintf(hex+2*i,3,"%02x",digest[i]);
    need(!strcmp(hex,expected),"DLC mod integrity mismatch");
}
static int mod_order(const void *a,const void *b) {return strcmp(((const DlcMod *)a)->name,((const DlcMod *)b)->name);}
static int mod_unchanged(int fd,const DlcMod *m) {
    struct stat st;const struct stat *s=&m->identity;
    return !fstat(fd,&st)&&S_ISREG(st.st_mode)&&st.st_dev==s->st_dev&&st.st_ino==s->st_ino&&st.st_size==s->st_size&&
        st.st_mtimespec.tv_sec==s->st_mtimespec.tv_sec&&st.st_mtimespec.tv_nsec==s->st_mtimespec.tv_nsec&&
        st.st_ctimespec.tv_sec==s->st_ctimespec.tv_sec&&st.st_ctimespec.tv_nsec==s->st_ctimespec.tv_nsec;
}
static size_t mod_lower(const Vol *v,const char *name) {
    size_t lo=0,hi=v->nmods;while(lo<hi){size_t m=lo+(hi-lo)/2;if(strcmp(v->mods[m].name,name)<0)lo=m+1;else hi=m;}return lo;
}
static void mods_load(Vol *v) {
    const char *root=getenv("TOTK_AOC_MODS"),*base=getenv("TOTK_ROMFS_MODS");char dir[4096],path[4200];
    if(root&&!strcmp(root,"0"))return;
    if(root&&*root)need(snprintf(dir,sizeof dir,"%s/%d",root,v->index)<(int)sizeof dir,"DLC mod path");
    else {if(!base||!*base||!strcmp(base,"0"))return;
        need(snprintf(dir,sizeof dir,"%s-aoc/%d",base,v->index)<(int)sizeof dir,"DLC mod path");}
    need(snprintf(path,sizeof path,"%s/manifest.tsv",dir)<(int)sizeof path,"DLC mod manifest path");
    FILE *f=fopen(path,"r");if(!f)return;char line[8192];size_t added=0;
    while(fgets(line,sizeof line,f)) {
        if(line[0]=='#'||line[0]=='\n')continue;
        char name[4096],sha[65],original[65];unsigned long long size;
        need(sscanf(line,"%4095[^\t]\t%llu\t%64[0-9a-f]\t%64[0-9a-f-]",name,&size,sha,original)==4&&
            strlen(sha)==64&&(strlen(original)==64||!strcmp(original,"-")),"DLC mod manifest line");
        need(romfs_path_valid_relative(name),"DLC mod relative path");uint64_t i=lower(v,name);
        int known=i<v->file_count&&!strcmp(name,entry_name(v,entry(v,i))),add=!strcmp(original,"-");
        need(known!=add,"DLC mod original/addition mismatch");
        if(known){Entry e=entry(v,i);hash_range(v->image_fd,e.offset,e.size,original);}else added++;
        need(snprintf(path,sizeof path,"%s/%s",dir,name)<(int)sizeof path,"DLC mod file path");
        int fd=open(path,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);struct stat st={0};
        need(fd>=0&&!fstat(fd,&st)&&S_ISREG(st.st_mode)&&(uint64_t)st.st_size==size,"DLC mod file missing or wrong size");
        DlcMod mod={strdup(name),strdup(path),size,st};need(mod.name&&mod.path,"DLC mod path allocation");
        hash_range(fd,0,size,sha);need(mod_unchanged(fd,&mod),"DLC mod changed during verification");close(fd);
        DlcMod *list=realloc(v->mods,(v->nmods+1)*sizeof(*list));need(list!=NULL,"DLC mod table");v->mods=list;v->mods[v->nmods++]=mod;
    }
    need(!ferror(f),"DLC mod manifest read");fclose(f);qsort(v->mods,v->nmods,sizeof(*v->mods),mod_order);
    for(size_t i=1;i<v->nmods;i++)need(strcmp(v->mods[i-1].name,v->mods[i].name)!=0,"duplicate DLC mod path");
    fprintf(stderr,"[botw] DLC mods %d checked: %zu files (%zu added) from %s\n",v->index,v->nmods,added,dir);
}
typedef struct { uint64_t size, dev, ino; int64_t mtime_s, mtime_ns, ctime_s, ctime_ns; char sha[65]; } Proof;
static Proof proof_for(const struct stat *s, const char *sha) {
    Proof p; memset(&p, 0, sizeof p); p.size = (uint64_t)s->st_size; p.dev = (uint64_t)s->st_dev; p.ino = (uint64_t)s->st_ino;
    p.mtime_s = s->st_mtimespec.tv_sec; p.mtime_ns = s->st_mtimespec.tv_nsec; p.ctime_s = s->st_ctimespec.tv_sec; p.ctime_ns = s->st_ctimespec.tv_nsec;
    snprintf(p.sha, sizeof p.sha, "%s", sha); return p;
}
/* The image's full SHA-256 once; afterwards a record of the file's identity (size, inode, times, expected hash) in the
   volume's folder (TOTK_ROMFS_PROOF_DIR elsewhere, as romfs.c); TOTK_ROMFS_VERIFY=full hashes again. */
static void verify_image(Vol *v, const char *dir) {
    const char *pdir = getenv("TOTK_ROMFS_PROOF_DIR"); if (pdir && *pdir) dir = pdir;
    struct stat st; need(fstat(v->image_fd, &st) == 0 && S_ISREG(st.st_mode) && (uint64_t)st.st_size == v->image_size, "add-on content image size");
    Proof want = proof_for(&st, v->image_sha), saved;
    char path[4096], tmp[4096]; need(snprintf(path, sizeof path, "%s/.aoc%d-verified-v1", dir, v->index) < (int)sizeof path, "add-on content proof path");
    int force = getenv("TOTK_ROMFS_VERIFY") && !strcmp(getenv("TOTK_ROMFS_VERIFY"), "full");
    int pf = open(path, O_RDONLY | O_NOFOLLOW);
    if (pf >= 0) { int ok = read(pf, &saved, sizeof saved) == (ssize_t)sizeof saved; close(pf);
        if (ok && !force && !memcmp(&saved, &want, sizeof want)) { fprintf(stderr, "[botw] add-on content %d unchanged; reused the SHA-256 verification record\n", v->index); return; } }
    char what[64]; snprintf(what, sizeof what, "%s %d", TOTK_UI("校验追加内容", "Verifying add-on content"), v->index);
    fprintf(stderr, "[botw] verifying add-on content %d SHA-256 (%llu bytes)%s\n", v->index, (unsigned long long)v->image_size, force ? " [forced]" : "");
    sha_fd(v->image_fd, v->image_sha, v->image_size, what);
    need(fstat(v->image_fd, &st) == 0 && (uint64_t)st.st_size == v->image_size, "add-on content image stat");
    Proof after = proof_for(&st, v->image_sha); need(!memcmp(&after, &want, sizeof want), "add-on content changed during verification");
    if (snprintf(tmp, sizeof tmp, "%s/.aoc%d-verified-v1.%ld.tmp", dir, v->index, (long)getpid()) >= (int)sizeof tmp) return;
    int out = open(tmp, O_WRONLY | O_CREAT | O_EXCL, 0600);
    if (out >= 0) { int ok = write(out, &want, sizeof want) == (ssize_t)sizeof want && fsync(out) == 0; close(out); if (!ok || rename(tmp, path) != 0) unlink(tmp); }
}
static void vol_load(Vol *v) {
    if (v->loaded) return;
    need(present(v), "add-on content not extracted");
    char dir[4096], path[4200]; vol_dir(v, dir, sizeof dir);
    need(snprintf(path, sizeof path, "%s/runtime-index.bin", dir) < (int)sizeof path, "add-on content index path");
    int fd = open(path, O_RDONLY); need(fd >= 0, "add-on content index missing (games/botw/scripts/extract_aoc_romfs.py, then make)");
    struct stat st; need(fstat(fd, &st) == 0 && st.st_size >= 24 && st.st_size < 64 * 1024 * 1024, "add-on content index size");
    sha_fd(fd, v->index_sha, 0, "index");
    v->index_size = (size_t)st.st_size; v->index_bytes = mmap(NULL, v->index_size, PROT_READ, MAP_PRIVATE, fd, 0); close(fd); need(v->index_bytes != MAP_FAILED, "map add-on content index");
    need(!memcmp(v->index_bytes, "TOTKRFS1", 8), "add-on content index format"); memcpy(&v->file_count, v->index_bytes + 8, 8); memcpy(&v->strings_offset, v->index_bytes + 16, 8);
    need(v->file_count < 1000000 && v->strings_offset == 24 + v->file_count * 24 && v->strings_offset < v->index_size, "add-on content index layout");
    const char *previous = NULL;
    for (uint64_t i = 0; i < v->file_count; i++) { Entry e = entry(v, i);
        need(e.offset <= v->image_size && e.size <= v->image_size - e.offset, "add-on content file bounds");
        need(e.name < v->index_size - v->strings_offset && e.len > 1 && e.len <= v->index_size - v->strings_offset - e.name, "add-on content name bounds");
        const char *n = entry_name(v, e); need(n[e.len - 1] == 0 && strlen(n) == e.len - 1 && romfs_path_valid_relative(n), "add-on content file name");
        need(!previous || strcmp(previous, n) < 0, "add-on content index order"); previous = n; }
    need(snprintf(path, sizeof path, "%s/romfs.bin", dir) < (int)sizeof path, "add-on content image path");
    v->image_fd = open(path, O_RDONLY); need(v->image_fd >= 0, "add-on content image missing");
    verify_image(v, dir);
    mods_load(v);
    v->loaded = 1;
    fprintf(stderr, "[botw] add-on content %d ready: %llu files, %llu bytes\n", v->index, (unsigned long long)v->file_count, (unsigned long long)v->image_size);
}
/* nn::aoc */
void runtime_aoc_announce(void) {
    int n = 0; for (int i = 0; i < AOC_MAX; i++) n += present(&vols[i]);
    fprintf(stderr, "[botw] add-on content: %d of %d packs extracted (TOTK_AOC: the folder holding <index>/romfs.bin)\n", n, AOC_MAX);
}
int runtime_aoc_count(void) { int n = 0; for (int i = 0; i < AOC_MAX; i++) n += present(&vols[i]); return n; }
int runtime_aoc_list(int *out, int offset, int count) {
    int n = 0, seen = 0;
    for (int i = 0; i < AOC_MAX && n < count; i++) { if (!present(&vols[i])) continue; if (seen++ < offset) continue; if (out) out[n] = vols[i].index; n++; }
    return n;
}
/* nn::fs */
unsigned runtime_aoc_cache_size(uint64_t *out, int index) { if (!out || index < 1 || index > AOC_MAX) return INVALID; *out = 0; return 0; }
unsigned runtime_aoc_mount(const char *name, int index, void *cache, uint64_t size) {
    (void)cache; (void)size;
    if (!name || !*name || strlen(name) >= sizeof vols[0].mount || strchr(name, '/') || strchr(name, ':') || index < 1 || index > AOC_MAX) return INVALID;
    Vol *v = &vols[index - 1]; if (!present(v)) return NOT_FOUND;
    vol_load(v);
    pthread_mutex_lock(&lock); snprintf(v->mount, sizeof v->mount, "%s", name); pthread_mutex_unlock(&lock);
    fprintf(stderr, "[botw] fs mount %s: -> add-on content %d\n", name, index);
    return 0;
}
static Vol *vol_of_path(const char *path, const char **rel) {
    if (!path) return NULL;
    for (int i = 0; i < AOC_MAX; i++) { Vol *v = &vols[i]; if (!v->loaded || !*v->mount) continue;
        size_t n = strlen(v->mount); if (strncmp(path, v->mount, n) || path[n] != ':') continue;
        if (rel) *rel = romfs_path_relative(v->mount, path); return v; }
    return NULL;
}
int runtime_aoc_owns(const char *path) { return vol_of_path(path, NULL) != NULL; }
int runtime_aoc_owns_name(const char *name) {
    if (!name) return 0;
    for (int i = 0; i < AOC_MAX; i++) if (vols[i].loaded && *vols[i].mount && !strcmp(vols[i].mount, name)) return 1;
    return 0;
}
void runtime_aoc_unmount(const char *name) {
    for (int i = 0; i < AOC_MAX; i++) if (vols[i].loaded && !strcmp(vols[i].mount, name)) { pthread_mutex_lock(&lock); vols[i].mount[0] = 0; pthread_mutex_unlock(&lock); fprintf(stderr, "[botw] fs unmount %s (add-on content %d)\n", name, vols[i].index); }
}
static uint64_t lower(const Vol *v, const char *name) { uint64_t lo = 0, hi = v->file_count; while (lo < hi) { uint64_t m = lo + (hi - lo) / 2; if (strcmp(entry_name(v, entry(v, m)), name) < 0) lo = m + 1; else hi = m; } return lo; }
unsigned runtime_aoc_open(uint64_t *out, const char *path, int mode) {
    const char *p = NULL; Vol *v = vol_of_path(path, &p);
    if (!out || mode != 1) return UNSUPPORTED;
    if (!v || !p) return NOT_FOUND;
    uint64_t i=lower(v,p);size_t m=mod_lower(v,p);int is_mod=m<v->nmods&&!strcmp(v->mods[m].name,p),fd=-1;
    if(is_mod){fd=open(v->mods[m].path,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);need(fd>=0&&mod_unchanged(fd,&v->mods[m]),"DLC mod file changed while the game ran");}
    else if(i>=v->file_count||strcmp(p,entry_name(v,entry(v,i))))return NOT_FOUND;
    pthread_mutex_lock(&lock);
    for(unsigned j=1;j<AOC_NH;j++)if(!handles[j].entry){handles[j].vol=(uint8_t)(v-vols);handles[j].entry=i+1;
        handles[j].mod=is_mod?(uint32_t)m+1:0;handles[j].fd=fd;*out=AOC_HANDLE_BASE+j;pthread_mutex_unlock(&lock);return 0;}
    pthread_mutex_unlock(&lock); runtime_fail("add-on content file handle table full"); return INVALID;
}
int runtime_aoc_handle(uint64_t h) { return h > AOC_HANDLE_BASE && h < AOC_HANDLE_BASE + AOC_NH; }
static int handle_entry(uint64_t h, Vol **v, Entry *e) {
    if (!runtime_aoc_handle(h)) return 0;
    pthread_mutex_lock(&lock); uint64_t i = handles[h - AOC_HANDLE_BASE].entry; uint8_t vi = handles[h - AOC_HANDLE_BASE].vol; pthread_mutex_unlock(&lock);
    if (!i) return 0; *v = &vols[vi]; uint32_t m=handles[h-AOC_HANDLE_BASE].mod;
    *e=m?(Entry){0,(*v)->mods[m-1].size,0,0}:entry(*v,i-1); return 1;
}
unsigned runtime_aoc_read(uint64_t *out, uint64_t h, int64_t offset, void *buffer, uint64_t size) {
    Vol *v; Entry e; if (!out || offset < 0 || !handle_entry(h, &v, &e)) return INVALID;
    if ((uint64_t)offset > e.size || (!buffer && size)) return INVALID;
    uint64_t n = size; if (n > e.size - (uint64_t)offset) n = e.size - (uint64_t)offset; uint64_t done = 0;
    uint32_t m=handles[h-AOC_HANDLE_BASE].mod;int fd=m?handles[h-AOC_HANDLE_BASE].fd:v->image_fd;
    if(m)need(mod_unchanged(fd,&v->mods[m-1]),"DLC mod file changed while the game ran");
    dm_guest_write_prepare(buffer, (size_t)n);
    while (done < n) { size_t chunk = (size_t)(n - done); if (chunk > 8 << 20) chunk = 8 << 20;
        ssize_t r = pread(fd, (uint8_t *)buffer + done, chunk, (off_t)(e.offset + (uint64_t)offset + done)); if (r <= 0) runtime_fail("add-on content read failure"); done += (uint64_t)r; }
    *out = done; return 0;
}
unsigned runtime_aoc_size(int64_t *out, uint64_t h) { Vol *v; Entry e; if (!out || !handle_entry(h, &v, &e)) return INVALID; *out = (int64_t)e.size; return 0; }
void runtime_aoc_close(uint64_t h) { Vol *v; Entry e; if (!handle_entry(h, &v, &e)) runtime_fail("close invalid add-on content handle"); pthread_mutex_lock(&lock); if(handles[h-AOC_HANDLE_BASE].mod)close(handles[h-AOC_HANDLE_BASE].fd);
    handles[h-AOC_HANDLE_BASE].entry=0;handles[h-AOC_HANDLE_BASE].mod=0; pthread_mutex_unlock(&lock); }
unsigned runtime_aoc_entry_type(int *out, const char *path) {
    const char *p = NULL; Vol *v = vol_of_path(path, &p); if (!out) return INVALID; if (!v || !p) return NOT_FOUND;
    size_t m=mod_lower(v,p);if(m<v->nmods&&!strcmp(v->mods[m].name,p)){*out=1;return 0;}
    uint64_t i = lower(v, p); if (i < v->file_count && !strcmp(entry_name(v, entry(v, i)), p)) { *out = 1; return 0; }
    char dir[4096]; if (snprintf(dir, sizeof dir, "%s/", p) >= (int)sizeof dir) return INVALID;
    i = lower(v, dir); if (i < v->file_count && !strncmp(entry_name(v, entry(v, i)), dir, strlen(dir))) { *out = 0; return 0; }
    m=mod_lower(v,dir);if(m<v->nmods&&!strncmp(v->mods[m].name,dir,strlen(dir))){*out=0;return 0;}
    return NOT_FOUND;
}
#endif
