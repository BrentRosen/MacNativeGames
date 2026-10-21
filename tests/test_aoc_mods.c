/* Synthetic DLC overlay regression: no player game files. */
#include <stdarg.h>
#include <assert.h>
#include <errno.h>
#include "../games/totk/runtime/aoc_romfs.c"
_Noreturn void runtime_fail(const char *s){fprintf(stderr,"failure: %s\n",s);exit(2);}
void runtime_boot_progress(const char *s,uint64_t a,uint64_t b){(void)s;(void)a;(void)b;}
void dm_guest_write_prepare(void *p,size_t n){(void)p;(void)n;}
static void contents(const char *path,const char *expected){
 uint64_t h,n;int64_t size;char b[64]={0};assert(!runtime_aoc_open(&h,path,1));assert(!runtime_aoc_size(&size,h));
 assert(size==(int64_t)strlen(expected));assert(!runtime_aoc_read(&n,h,0,b,sizeof b));assert(n==strlen(expected)&&!memcmp(b,expected,n));
 assert(!runtime_aoc_read(&n,h,size,b,sizeof b)&&!n);assert(runtime_aoc_read(&n,h,size+1,b,1)==INVALID);runtime_aoc_close(h);
}
int main(int argc,char **argv){
 assert(argc==5);Vol *v=&vols[0];v->image_fd=open(argv[1],O_RDONLY);assert(v->image_fd>=0);
 int fd=open(argv[2],O_RDONLY);struct stat st;assert(!fstat(fd,&st));v->index_size=st.st_size;v->index_bytes=mmap(NULL,st.st_size,PROT_READ,MAP_PRIVATE,fd,0);close(fd);
 memcpy(&v->file_count,v->index_bytes+8,8);memcpy(&v->strings_offset,v->index_bytes+16,8);v->loaded=1;
 int vanilla=!strcmp(argv[4],"vanilla");
 if(!strcmp(argv[4],"implicit"))setenv("TOTK_ROMFS_MODS",argv[3],1);
 else setenv("TOTK_AOC_MODS",vanilla?"0":argv[3],1);
 mods_load(v);assert(!runtime_aoc_mount("aoc",1,NULL,0));
 contents("aoc:/Base.bin",vanilla?"ORIGINAL":"MODDATA");contents("aoc:/Keep.bin","KEEP");
 if(!vanilla){int type;assert(!runtime_aoc_entry_type(&type,"aoc:/Added")&&type==0);
  contents("aoc:////Added/New.bin","ADDED");assert(!runtime_aoc_entry_type(&type,"aoc:/Added/New.bin")&&type==1);
  if(!strcmp(argv[4],"mutate")){uint64_t h,n;char b[20];assert(!runtime_aoc_open(&h,"aoc:/Base.bin",1));
   assert(!truncate(v->mods[mod_lower(v,"Base.bin")].path,99));runtime_aoc_read(&n,h,0,b,sizeof b);abort();}
 }
 uint64_t h;assert(runtime_aoc_open(&h,"aoc:/../Base.bin",1)==NOT_FOUND);assert(runtime_aoc_open(&h,"aoc:/Base.bin",2)==UNSUPPORTED);
 for(int i=0;i<2100;i++){assert(!runtime_aoc_open(&h,"aoc:/Keep.bin",1));runtime_aoc_close(h);}
 puts("DLC originals, replacements, additions, directory types, paths and handles passed");return 0;
}
