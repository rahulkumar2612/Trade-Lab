function localize()
{
  var t = document.querySelector("local-time");
  var d=new Date(t+" UTC");
  document.write(d.toString());
}
localize();
